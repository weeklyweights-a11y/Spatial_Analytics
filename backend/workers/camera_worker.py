"""Camera worker — DEIMv2 + tracking + identity + zones + Redis events."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
import supervision as sv
from loguru import logger

from backend.config import get_settings
from backend.core.activity_classifier import ActivityClassifier
from backend.core.face_matcher import FaceMatcher
from backend.core.identity_linker import IdentityLinker
from backend.core.person_detector import PersonDetector
from backend.core.person_tracker import PersonTracker
from backend.core.zone_classifier import ZoneClassifier
from backend.db import redis_sync
from backend.utils.participant_names import ParticipantNameCache
from backend.utils.stream import frame_generator_with_reconnect
from backend.utils.zone_loader import load_zones_yaml, zones_for_camera

ACTIVITY_COLORS = {
    "coding": "#22c55e",
    "collaborating": "#3b82f6",
    "mentoring": "#f97316",
    "presenting": "#a855f7",
    "idle": "#6b7280",
    "eating": "#6b7280",
    "resting": "#6b7280",
    "sponsor_engagement": "#6b7280",
    "networking": "#6b7280",
}


def _hex_bgr(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)


class CameraWorker:
    """Single-camera processing loop."""

    def __init__(self, camera_id: str, rtsp_url: str) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.settings = get_settings()
        self._shutdown = False
        self._status = "active"
        self._frames_processed = 0
        self._face_timestamps: deque[float] = deque()
        self._last_heartbeat = 0.0
        self._last_stats_log = 0.0
        self._last_processed_at = 0.0
        self._fps_window: deque[float] = deque(maxlen=30)
        self._faiss_mtimes = (0.0, 0.0)
        self._frame_index = 0

        self.detector = PersonDetector()
        self.tracker = PersonTracker()
        self.face_matcher = FaceMatcher()
        self.face_matcher.load()
        self.linker = IdentityLinker(face_matcher=self.face_matcher, name_cache=ParticipantNameCache())
        self.activity = ActivityClassifier()

        zones = zones_for_camera(load_zones_yaml(), camera_id)
        self.zone_classifier = ZoneClassifier(zones)
        logger.info(
            "Camera worker started: camera_id={}, rtsp_url={}, zones_loaded={}",
            camera_id,
            rtsp_url,
            len(zones),
        )

        track_color = sv.ColorLookup.TRACK
        self.label_annotator = sv.LabelAnnotator(
            text_scale=0.5, text_thickness=1, color_lookup=track_color
        )
        self.trace_annotator = sv.TraceAnnotator(
            thickness=2, trace_length=30, color_lookup=track_color
        )
        self.heatmap_annotator = sv.HeatMapAnnotator()

        self._index_path = Path(self.settings.FAISS_INDEX_PATH)
        self._map_path = Path(self.settings.EMBEDDING_MAP_PATH)
        self._update_faiss_mtimes()

    def _update_faiss_mtimes(self) -> None:
        idx_m = self._index_path.stat().st_mtime if self._index_path.exists() else 0.0
        map_m = self._map_path.stat().st_mtime if self._map_path.exists() else 0.0
        self._faiss_mtimes = self.linker.reload_faiss_if_needed(idx_m, map_m, self._faiss_mtimes)

    def request_shutdown(self) -> None:
        self._shutdown = True

    def _set_status(self, status: str) -> None:
        self._status = status

    def _record_faces(self, count: int) -> None:
        now = time.monotonic()
        for _ in range(count):
            self._face_timestamps.append(now)
        cutoff = now - 60.0
        while self._face_timestamps and self._face_timestamps[0] < cutoff:
            self._face_timestamps.popleft()

    def _faces_last_minute(self) -> int:
        now = time.monotonic()
        cutoff = now - 60.0
        while self._face_timestamps and self._face_timestamps[0] < cutoff:
            self._face_timestamps.popleft()
        return len(self._face_timestamps)

    def _maybe_heartbeat(self, persons_tracked: int) -> None:
        now = time.monotonic()
        if now - self._last_heartbeat < self.settings.CAMERA_HEARTBEAT_SECONDS:
            return
        fps = sum(self._fps_window) / len(self._fps_window) if self._fps_window else 0.0
        redis_sync.set_camera_heartbeat(
            self.camera_id,
            {
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                "fps": f"{fps:.1f}",
                "frames_processed": self._frames_processed,
                "faces_detected": self._faces_last_minute(),
                "persons_tracked": persons_tracked,
                "status": self._status,
            },
        )
        self._last_heartbeat = now

    def _maybe_stats_log(self, detections: sv.Detections) -> None:
        now = time.monotonic()
        if now - self._last_stats_log < 60.0:
            return
        identified = 0
        if detections.tracker_id is not None:
            for tid in detections.tracker_id:
                if tid is None:
                    continue
                pid, _ = self.linker.get_participant(int(tid))
                if pid:
                    identified += 1
        fps = sum(self._fps_window) / len(self._fps_window) if self._fps_window else 0.0
        zone_counts = self.zone_classifier.trigger_occupancy(detections)
        logger.info(
            "Pipeline stats: camera_id={}, fps={:.1f}, persons={}, identified={}, unidentified={}, zones={}",
            self.camera_id,
            fps,
            len(detections),
            identified,
            len(detections) - identified,
            zone_counts,
        )
        self._last_stats_log = now

    def _should_process_frame(self) -> bool:
        now = time.monotonic()
        min_interval = 1.0 / self.settings.CAMERA_TARGET_FPS
        if now - self._last_processed_at < min_interval:
            return False
        self._last_processed_at = now
        return True

    def _annotate_frame(
        self, frame: np.ndarray, detections: sv.Detections, activities: list[str]
    ) -> np.ndarray:
        annotated = frame.copy()
        for zcfg, poly in self.zone_classifier.zone_polygons():
            overlay = annotated.copy()
            cv2.fillPoly(overlay, [poly], _hex_bgr("#6b7280"))
            cv2.addWeighted(overlay, 0.15, annotated, 0.85, 0, annotated)
            cv2.polylines(annotated, [poly], True, _hex_bgr("#6b7280"), 2)

        if detections.is_empty():
            return annotated

        tracker_ids = detections.tracker_id
        if tracker_ids is None:
            tracker_ids = []
        labels = []
        for i, tid in enumerate(tracker_ids):
            act = activities[i] if i < len(activities) else "idle"
            name = self.linker.get_display_name(int(tid)) if tid is not None else "Unknown"
            labels.append(f"{name} | {act}")
            x1, y1, x2, y2 = detections.xyxy[i].astype(int)
            color = _hex_bgr(ACTIVITY_COLORS.get(act, "#6b7280"))
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

        annotated = self.trace_annotator.annotate(scene=annotated, detections=detections)
        annotated = self.heatmap_annotator.annotate(scene=annotated, detections=detections)
        annotated = self.label_annotator.annotate(scene=annotated, detections=detections, labels=labels)
        return annotated

    def _publish_tracking(
        self,
        detections: sv.Detections,
        activities: list[str],
        scale: float,
        frame_width: int,
        frame_height: int,
    ) -> None:
        """Publish bbox overlay data in MJPEG output coordinate space."""
        persons: list[dict[str, Any]] = []
        if detections.is_empty() or detections.tracker_id is None:
            payload = {
                "type": "tracking",
                "camera_id": self.camera_id,
                "persons": persons,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            redis_sync.publish_tracking_update(self.camera_id, payload)
            return

        for i, tid in enumerate(detections.tracker_id):
            x1, y1, x2, y2 = detections.xyxy[i].tolist()
            bbox = [x1 * scale, y1 * scale, x2 * scale, y2 * scale]
            track_id = int(tid) if tid is not None else -1
            pid, sim = self.linker.get_participant(track_id)
            act = activities[i] if i < len(activities) else "idle"
            name = self.linker.get_display_name(track_id) if tid is not None else "Unknown"
            person: dict[str, Any] = {
                "track_id": track_id,
                "participant_id": pid,
                "name": name,
                "bbox": bbox,
                "activity": act,
                "confidence": float(sim) if pid else 0.0,
                "frame_width": frame_width,
                "frame_height": frame_height,
            }
            persons.append(person)

        payload = {
            "type": "tracking",
            "camera_id": self.camera_id,
            "persons": persons,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        redis_sync.publish_tracking_update(self.camera_id, payload)

    def _process_frame(self, frame: np.ndarray) -> None:
        t0 = time.monotonic()
        try:
            boxes, scores, keypoints = self.detector.detect(frame)
        except Exception as exc:
            logger.error("DEIMv2 inference failed: camera_id={}, error={}", self.camera_id, exc)
            raise

        detections = self.tracker.update(boxes, scores, keypoints)
        self._frame_index += 1

        if self._frame_index % self.settings.FACE_RECOGNITION_INTERVAL_FRAMES == 0:
            self._update_faiss_mtimes()
            faces = self.linker.update_identities(frame, detections, self.camera_id)
            self._record_faces(faces)
        self.linker.log_unidentified_timeouts(detections)

        zone_assignments = self.zone_classifier.assign_zones(detections)
        occupancy = self.zone_classifier.trigger_occupancy(detections)
        for zone_name, count in occupancy.items():
            redis_sync.update_zone_occupancy(zone_name, count)

        activities: list[str] = []
        if detections.tracker_id is not None:
            for i, tid in enumerate(detections.tracker_id):
                kp = None
                if detections.data is not None and "keypoints" in detections.data:
                    kps = detections.data["keypoints"]
                    if i < len(kps):
                        kp = kps[i]
                ztype = zone_assignments[i].zone_type if i < len(zone_assignments) else "unknown"
                track_id = int(tid) if tid is not None else -1
                act = self.activity.classify(track_id, ztype, kp)
                activities.append(act)

                pid, sim = self.linker.get_participant(track_id)
                if pid:
                    zname = zone_assignments[i].zone_name if i < len(zone_assignments) else "unassigned"
                    bbox = detections.xyxy[i].tolist()
                    event = {
                        "participant_id": pid,
                        "camera_id": self.camera_id,
                        "zone": zname,
                        "zone_type": ztype,
                        "activity": act,
                        "track_id": track_id,
                        "bbox": bbox,
                        "confidence": sim,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    redis_sync.push_activity_event(event)
                    redis_sync.update_participant_state(
                        pid,
                        zname,
                        act,
                        0.0,
                        last_seen=datetime.now(timezone.utc).isoformat(),
                    )

        annotated = self._annotate_frame(frame, detections, activities)
        h, w = annotated.shape[:2]
        scale = 1.0
        out_w, out_h = w, h
        if w > 1280:
            scale = 1280 / w
            out_w = 1280
            out_h = int(h * scale)
            annotated = cv2.resize(annotated, (out_w, out_h))
        self._publish_tracking(detections, activities, scale, out_w, out_h)
        _, jpeg = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        redis_sync.set_camera_frame(
            self.camera_id,
            jpeg.tobytes(),
            ttl_seconds=self.settings.CAMERA_FRAME_TTL_SECONDS,
        )

        self._frames_processed += 1
        elapsed = time.monotonic() - t0
        if elapsed > 0:
            self._fps_window.append(1.0 / elapsed)
        self._maybe_heartbeat(len(detections))
        self._maybe_stats_log(detections)

    def run(self) -> None:
        def on_reconnecting() -> None:
            self._set_status("reconnecting")

        def on_reconnected(downtime: float) -> None:
            self._set_status("active")
            logger.info("RTSP reconnected: camera_id={}, downtime_seconds={:.1f}", self.camera_id, downtime)
            self.tracker.reset()

        def on_persistent_failure() -> None:
            self._set_status("error")

        for frame in frame_generator_with_reconnect(
            self.rtsp_url,
            on_reconnecting=on_reconnecting,
            on_reconnected=on_reconnected,
            on_persistent_failure=on_persistent_failure,
        ):
            if self._shutdown:
                break
            if not self._should_process_frame():
                continue
            self._process_frame(frame)

        self._flush_shutdown_state()
        logger.info("Camera worker shutdown: camera_id={}", self.camera_id)
        redis_sync.close_sync_redis()
        self.linker.name_cache.close()

    def _flush_shutdown_state(self) -> None:
        """Write final heartbeat before exit (SIGTERM graceful shutdown)."""
        fps = sum(self._fps_window) / len(self._fps_window) if self._fps_window else 0.0
        redis_sync.set_camera_heartbeat(
            self.camera_id,
            {
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                "fps": f"{fps:.1f}",
                "frames_processed": self._frames_processed,
                "faces_detected": self._faces_last_minute(),
                "persons_tracked": 0,
                "status": "shutdown",
            },
        )


def _configure_worker_logging(camera_id: str, level: str) -> None:
    """Structured JSON logs for camera worker processes."""

    def json_sink(message: Any) -> None:
        record = message.record
        payload = {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "service": "camera-worker",
            "camera_id": camera_id,
            "message": record["message"],
        }
        print(json.dumps(payload), file=sys.stderr)

    logger.remove()
    logger.add(json_sink, level=level)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="SpatialScore camera worker")
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--rtsp-url", required=True)
    args = parser.parse_args(argv)

    settings = get_settings()
    _configure_worker_logging(args.camera_id, settings.LOG_LEVEL)

    worker = CameraWorker(camera_id=args.camera_id, rtsp_url=args.rtsp_url)

    def _handle_sigterm(_signum: int, _frame: Any) -> None:
        worker.request_shutdown()

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)
    worker.run()


if __name__ == "__main__":
    main()
