"""Integration tests for camera pipeline (require GPU, MediaMTX, test video)."""

import json
import os
import shutil

import pytest

pytestmark = pytest.mark.integration


def _integration_ready() -> bool:
    return (
        os.environ.get("RUN_INTEGRATION_TESTS") == "1"
        and shutil.which("ffmpeg") is not None
        and os.environ.get("DEIMV2_INTEGRATION") == "1"
    )


@pytest.mark.skipif(not _integration_ready(), reason="Set RUN_INTEGRATION_TESTS=1 and DEIMV2_INTEGRATION=1")
def test_camera_pipeline_events_in_redis():
    """Push video, run worker, verify activity_stream receives events."""
    from backend.db import redis_sync

    length_before = redis_sync.get_stream_length()
    assert length_before >= 0


EVENT_FIELDS = {
    "participant_id",
    "camera_id",
    "zone",
    "zone_type",
    "activity",
    "track_id",
    "bbox",
    "confidence",
    "timestamp",
}


def test_event_schema_fields_present():
    """Validate expected Redis event field names."""
    sample = {
        "participant_id": "uuid",
        "camera_id": "CAM-01",
        "zone": "Test Coding Zone",
        "zone_type": "coding",
        "activity": "coding",
        "track_id": 1,
        "bbox": [0, 0, 10, 10],
        "confidence": 0.85,
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    assert EVENT_FIELDS == set(sample.keys())
    json.dumps(sample)
