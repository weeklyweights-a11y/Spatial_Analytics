"""Unit tests for identity_linker."""

import time

import numpy as np
import supervision as sv
from unittest.mock import MagicMock

from backend.core.face_detector import Face
from backend.core.identity_linker import IdentityLinker, TrackIdentity


class StubDetector:
    def detect(self, image, threshold=0.5):
        h, w = image.shape[:2]
        return [
            Face(
                bbox=np.array([w * 0.35, h * 0.2, w * 0.55, h * 0.45], dtype=np.float32),
                confidence=0.99,
                landmarks=np.array(
                    [[w * 0.4, h * 0.3], [w * 0.5, h * 0.3], [w * 0.45, h * 0.35], [w * 0.4, h * 0.4], [w * 0.5, h * 0.4]],
                    dtype=np.float32,
                ),
            )
        ]


class StubRecognizer:
    def align_face(self, image, landmarks, size=112):
        import cv2
        return cv2.resize(image, (size, size))

    def embed(self, aligned_face):
        emb = np.ones(512, dtype=np.float32)
        emb /= np.linalg.norm(emb)
        return emb


class StubMatcher:
    def search(self, embedding, k=1):
        return 0.85, 0

    def get_participant_id(self, index_pos):
        return "participant-uuid-1" if index_pos >= 0 else None

    def load(self):
        pass


def _body_detections():
    return sv.Detections(
        xyxy=np.array([[100, 50, 300, 400]], dtype=np.float32),
        confidence=np.array([0.9], dtype=np.float32),
        tracker_id=np.array([42], dtype=int),
    )


def test_face_in_body_links_track():
    linker = IdentityLinker(
        face_detector=StubDetector(),
        face_recognizer=StubRecognizer(),
        face_matcher=StubMatcher(),
        name_cache=MagicMock(get_name=lambda pid: "Test User"),
    )
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    det = _body_detections()
    linker.update_identities(frame, det, "CAM-01")
    pid, sim = linker.get_participant(42)
    assert pid == "participant-uuid-1"
    assert sim >= 0.5


def test_face_outside_body_no_link():
    linker = IdentityLinker(
        face_detector=StubDetector(),
        face_recognizer=StubRecognizer(),
        face_matcher=StubMatcher(),
    )
    det = sv.Detections(
        xyxy=np.array([[500, 50, 700, 400]], dtype=np.float32),
        confidence=np.array([0.9], dtype=np.float32),
        tracker_id=np.array([99], dtype=int),
    )
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    linker.update_identities(frame, det, "CAM-01")
    pid, _ = linker.get_participant(99)
    assert pid is None


def test_track_lost_clears_cache():
    linker = IdentityLinker(
        face_detector=StubDetector(),
        face_recognizer=StubRecognizer(),
        face_matcher=StubMatcher(),
    )
    linker._cache[7] = TrackIdentity(participant_id="p1", similarity=0.9)
    empty = sv.Detections.empty()
    linker.sync_active_tracks(empty)
    assert 7 not in linker._cache


class LowSimMatcher(StubMatcher):
    def search(self, embedding, k=1):
        return 0.3, 0


def test_no_participant_when_similarity_below_threshold():
    linker = IdentityLinker(
        face_detector=StubDetector(),
        face_recognizer=StubRecognizer(),
        face_matcher=LowSimMatcher(),
    )
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    linker.update_identities(frame, _body_detections(), "CAM-01")
    pid, _ = linker.get_participant(42)
    assert pid is None


def test_unidentified_timeout_logged_once():
    linker = IdentityLinker(
        face_detector=StubDetector(),
        face_recognizer=StubRecognizer(),
        face_matcher=LowSimMatcher(),
    )
    linker._timeout = 0.01
    det = _body_detections()
    linker.sync_active_tracks(det)
    time.sleep(0.02)
    linker.log_unidentified_timeouts(det)
    assert 42 in linker._timeout_logged
    linker.log_unidentified_timeouts(det)
    assert len(linker._timeout_logged) == 1
