"""Unit tests for person_tracker."""

import numpy as np

from backend.core.person_tracker import PersonTracker


def test_track_id_persists_across_frames():
    tracker = PersonTracker()
    boxes = np.array([[100, 100, 200, 300]], dtype=np.float32)
    scores = np.array([0.9], dtype=np.float32)
    kpts = np.zeros((1, 49, 3), dtype=np.float32)

    ids = []
    for dx in (0, 5, 10):
        b = boxes.copy()
        b[:, [0, 2]] += dx
        det = tracker.update(b, scores, kpts)
        if det.tracker_id is not None and len(det.tracker_id):
            ids.append(int(det.tracker_id[0]))

    assert len(ids) == 3
    assert ids[0] == ids[1] == ids[2]
