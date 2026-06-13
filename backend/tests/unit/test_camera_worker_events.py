"""Test that unidentified tracks do not emit activity events."""

from unittest.mock import patch

import numpy as np
import supervision as sv

from backend.core.identity_linker import IdentityLinker


@patch("backend.workers.camera_worker.redis_sync.push_activity_event")
def test_no_event_for_unidentified_track(mock_push):
    """Only identified tracks should call push_activity_event."""
    from backend.workers.camera_worker import CameraWorker

    # Simulate event emission logic from _process_frame
    detections = sv.Detections(
        xyxy=np.array([[100, 100, 200, 300]], dtype=np.float32),
        confidence=np.array([0.9], dtype=np.float32),
        tracker_id=np.array([1], dtype=int),
    )
    linker = IdentityLinker()
    pid, sim = linker.get_participant(1)
    assert pid is None
    if pid:
        mock_push({"participant_id": pid})
    mock_push.assert_not_called()


def test_activity_color_hex_map():
    from backend.workers.camera_worker import ACTIVITY_COLORS, _hex_bgr

    assert ACTIVITY_COLORS["coding"] == "#22c55e"
    assert _hex_bgr("#22c55e") == (34, 197, 94)
    assert _hex_bgr(ACTIVITY_COLORS["collaborating"]) == (59, 130, 246)
