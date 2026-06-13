"""Face-to-track identity linking using Phase 1 face pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import supervision as sv
from loguru import logger

from backend.config import get_settings
from backend.core.face_detector import FaceDetector
from backend.core.face_matcher import FaceMatcher
from backend.core.face_recognizer import FaceRecognizer
from backend.utils.geometry import bbox_contains_point, bbox_iou, face_center
from backend.utils.participant_names import ParticipantNameCache


@dataclass
class TrackIdentity:
    participant_id: Optional[str] = None
    similarity: float = 0.0
    last_seen: float = field(default_factory=time.monotonic)
    identified_at: Optional[float] = None


class IdentityLinker:
    """Maps ByteTrack tracker_id to participant UUID via periodic face recognition."""

    def __init__(
        self,
        face_detector: Optional[FaceDetector] = None,
        face_recognizer: Optional[FaceRecognizer] = None,
        face_matcher: Optional[FaceMatcher] = None,
        name_cache: Optional[ParticipantNameCache] = None,
    ) -> None:
        settings = get_settings()
        self._threshold = settings.FACE_SIMILARITY_THRESHOLD
        self._timeout = settings.UNIDENTIFIED_TIMEOUT_SECONDS
        self._low_confidence_margin = 0.05
        self.face_detector = face_detector or FaceDetector()
        self.face_recognizer = face_recognizer or FaceRecognizer()
        self.face_matcher = face_matcher or FaceMatcher()
        self.name_cache = name_cache or ParticipantNameCache()
        self._cache: dict[int, TrackIdentity] = {}
        self._track_first_seen: dict[int, float] = {}
        self._timeout_logged: set[int] = set()

    def reload_faiss_if_needed(self, index_mtime: float, map_mtime: float, last_mtimes: tuple[float, float]) -> tuple[float, float]:
        """Reload FAISS when either file changed."""
        if (index_mtime, map_mtime) != last_mtimes and (index_mtime > 0 or map_mtime > 0):
            self.face_matcher.load()
            return index_mtime, map_mtime
        return last_mtimes

    def sync_active_tracks(self, detections: sv.Detections) -> None:
        """Drop cache entries for lost tracks."""
        now = time.monotonic()
        active: set[int] = set()
        if detections.tracker_id is not None:
            for tid in detections.tracker_id:
                if tid is not None:
                    track_id = int(tid)
                    active.add(track_id)
                    if track_id not in self._track_first_seen:
                        self._track_first_seen[track_id] = now
        for tid in list(self._cache.keys()):
            if tid not in active:
                del self._cache[tid]
        for tid in list(self._track_first_seen.keys()):
            if tid not in active:
                del self._track_first_seen[tid]
                self._timeout_logged.discard(tid)

    def log_unidentified_timeouts(self, detections: sv.Detections) -> None:
        """Log once per track that remains unidentified past UNIDENTIFIED_TIMEOUT_SECONDS."""
        if detections.tracker_id is None:
            return
        now = time.monotonic()
        for tid in detections.tracker_id:
            if tid is None:
                continue
            track_id = int(tid)
            if track_id in self._timeout_logged:
                continue
            first_seen = self._track_first_seen.get(track_id, now)
            entry = self._cache.get(track_id)
            if entry and entry.participant_id:
                continue
            if now - first_seen < self._timeout:
                continue
            self._timeout_logged.add(track_id)
            logger.debug(
                "Track unidentified after timeout: track_id={}, timeout_seconds={}",
                track_id,
                self._timeout,
            )

    def _match_face_to_body(
        self, face_bbox: np.ndarray, body_boxes: np.ndarray, body_tracker_ids: np.ndarray
    ) -> Optional[int]:
        fx, fy = face_center(face_bbox)
        candidates: list[tuple[int, float]] = []
        for i, body in enumerate(body_boxes):
            if not bbox_contains_point(body, fx, fy):
                continue
            tid = int(body_tracker_ids[i]) if body_tracker_ids[i] is not None else -1
            if tid < 0:
                continue
            upper = body.copy()
            upper[3] = body[1] + (body[3] - body[1]) * 0.5
            iou = bbox_iou(face_bbox, upper)
            candidates.append((tid, iou))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def update_identities(
        self, frame: np.ndarray, detections: sv.Detections, camera_id: str
    ) -> int:
        """Run face pipeline; return number of faces detected this cycle."""
        self.sync_active_tracks(detections)
        if detections.is_empty() or detections.tracker_id is None:
            return 0

        faces = self.face_detector.detect(frame)
        face_count = len(faces)
        for face in faces:
            track_id = self._match_face_to_body(
                face.bbox, detections.xyxy, detections.tracker_id
            )
            if track_id is None:
                continue

            aligned = self.face_recognizer.align_face(frame, face.landmarks)
            embedding = self.face_recognizer.embed(aligned)
            sim, idx = self.face_matcher.search(embedding)
            if idx < 0 or sim < self._threshold:
                continue

            participant_id = self.face_matcher.get_participant_id(idx)
            if not participant_id:
                continue

            name = self.name_cache.get_name(participant_id) or participant_id
            if self._threshold <= sim < self._threshold + self._low_confidence_margin:
                logger.warning(
                    "Low confidence match: track_id={}, similarity={:.2f}, threshold={}, participant={}",
                    track_id,
                    sim,
                    self._threshold,
                    name,
                )
            else:
                logger.info(
                    "Identity linked: track_id={}, participant={} ({}), similarity={:.2f}",
                    track_id,
                    name,
                    participant_id,
                    sim,
                )

            now = time.monotonic()
            self._cache[track_id] = TrackIdentity(
                participant_id=participant_id,
                similarity=sim,
                last_seen=now,
                identified_at=now,
            )
        return face_count

    def get_participant(self, track_id: int) -> tuple[Optional[str], float]:
        """Return (participant_id, similarity) for track."""
        entry = self._cache.get(track_id)
        if entry is None:
            return None, 0.0
        entry.last_seen = time.monotonic()
        return entry.participant_id, entry.similarity

    def get_display_name(self, track_id: int) -> str:
        pid, _ = self.get_participant(track_id)
        if not pid:
            return "Unknown"
        return self.name_cache.get_name(pid) or "Unknown"

    def clear_track(self, track_id: int) -> None:
        self._cache.pop(track_id, None)
