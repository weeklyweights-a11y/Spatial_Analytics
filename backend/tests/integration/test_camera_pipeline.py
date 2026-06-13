"""Integration tests for camera pipeline (require GPU, MediaMTX, test video)."""

from __future__ import annotations

import json
import os
import time

import pytest

from backend.db import redis_sync
from backend.tests.integration.pipeline_helpers import (
    deimv2_model_path,
    ffmpeg_available,
    gpu_pipeline_enabled,
    gpu_prerequisites_met,
    gpu_skip_reason,
    integration_enabled,
    read_video_frame,
    redis_available,
    skip_reason,
    start_camera_worker,
    start_rtmp_simulator,
    test_video_path,
    wait_for,
)

pytestmark = pytest.mark.integration


def test_event_schema_fields_present():
    """Validate expected Redis event field names (no external services)."""
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
    assert redis_sync.EVENT_FIELD_NAMES == set(sample.keys())
    json.dumps(sample)


@pytest.mark.skipif(not integration_enabled(), reason=skip_reason())
@pytest.mark.skipif(not redis_available(), reason="Redis not reachable")
def test_activity_event_redis_roundtrip():
    """push_activity_event writes all required fields readable via XREAD."""
    from backend.config import get_settings

    get_settings.cache_clear()
    marker = f"pytest-{time.time()}"
    event = {
        "participant_id": marker,
        "camera_id": "CAM-01",
        "zone": "Test Coding Zone",
        "zone_type": "coding",
        "activity": "coding",
        "track_id": 99,
        "bbox": [1.0, 2.0, 3.0, 4.0],
        "confidence": 0.91,
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    length_before = redis_sync.get_stream_length()
    redis_sync.push_activity_event(event)
    assert redis_sync.get_stream_length() >= length_before + 1

    events = redis_sync.read_activity_events(count=20)
    match = next((e for e in reversed(events) if e.get("participant_id") == marker), None)
    assert match is not None, "Pushed event not found in activity_stream"
    redis_sync.validate_activity_event(match)
    assert match["confidence"] == pytest.approx(0.91)
    assert match["bbox"] == [1.0, 2.0, 3.0, 4.0]


@pytest.mark.skipif(not gpu_pipeline_enabled(), reason=gpu_skip_reason())
@pytest.mark.skipif(not gpu_prerequisites_met(), reason="Missing DEIMv2 model, test video, ffmpeg, or Redis")
def test_deimv2_model_loads_and_returns_49_keypoints():
    """DEIMv2 ONNX loads and returns correct keypoint shape on a test video frame."""
    from backend.config import get_settings
    from backend.core.person_detector import PersonDetector

    get_settings.cache_clear()
    frame = read_video_frame(test_video_path(), frame_index=0)
    detector = PersonDetector(model_path=deimv2_model_path())
    boxes, scores, keypoints = detector.detect(frame)
    assert boxes.ndim == 2 and boxes.shape[1] == 4
    assert scores.ndim == 1
    assert keypoints.shape[1:] == (49, 3)
    if len(boxes) > 0:
        assert float(scores.max()) >= 0.0


@pytest.mark.skipif(not gpu_pipeline_enabled(), reason=gpu_skip_reason())
@pytest.mark.skipif(not gpu_prerequisites_met(), reason="Missing DEIMv2 model, test video, ffmpeg, or Redis")
def test_camera_worker_writes_heartbeat_and_frame():
    """Live worker publishes camera_status and camera_frame within 90 seconds."""
    from backend.config import get_settings

    get_settings.cache_clear()
    redis_sync.close_sync_redis()

    camera_id = os.environ.get("TEST_CAMERA_ID", "CAM-01")
    rtmp_cam = os.environ.get("TEST_RTMP_CAMERA_ID", "cam01")
    rtsp_host = os.environ.get("MEDIAMTX_HOST", "127.0.0.1")
    rtsp_url = f"rtsp://{rtsp_host}:8554/{rtmp_cam}"
    video = test_video_path()

    stream_len_before = redis_sync.get_stream_length()

    with start_rtmp_simulator(video, camera_id=rtmp_cam, host=rtsp_host) as stream_proc:
        time.sleep(3)
        with start_camera_worker(camera_id=camera_id, rtsp_url=rtsp_url) as worker_proc:
            assert worker_proc.proc is not None
            heartbeat_ok = wait_for(
                lambda: redis_sync.get_camera_status(camera_id).get("status") in {"active", "reconnecting"},
                timeout_seconds=90,
                description="camera heartbeat",
            )
            assert heartbeat_ok, redis_sync.get_camera_status(camera_id)

            frame_ok = wait_for(
                lambda: redis_sync.get_camera_frame(camera_id) is not None,
                timeout_seconds=90,
                description="camera_frame key",
            )
            assert frame_ok, "camera_frame not written to Redis"

            status = redis_sync.get_camera_status(camera_id)
            assert status.get("fps"), f"heartbeat missing fps: {status}"
            assert status.get("frames_processed"), f"heartbeat missing frames_processed: {status}"

            jpeg = redis_sync.get_camera_frame(camera_id)
            assert jpeg is not None and len(jpeg) > 1000
            ttl = redis_sync.get_camera_frame_ttl(camera_id)
            assert 0 < ttl <= 5

            occupancy = redis_sync.get_zone_occupancy()
            assert isinstance(occupancy, dict)

            # Stream may stay at prior length if no registered faces — occupancy/frame prove pipeline runs.
            _ = stream_len_before


@pytest.mark.skipif(not gpu_pipeline_enabled(), reason=gpu_skip_reason())
@pytest.mark.skipif(not gpu_prerequisites_met(), reason="Missing DEIMv2 model, test video, ffmpeg, or Redis")
def test_camera_pipeline_events_in_redis_when_identified():
    """When FAISS has embeddings, worker emits validated activity events within 90 seconds."""
    from backend.config import get_settings

    get_settings.cache_clear()
    redis_sync.close_sync_redis()

    index_path = os.environ.get(
        "FAISS_INDEX_PATH",
        str(test_video_path().parents[1] / "data" / "faiss" / "faiss_index.bin"),
    )
    if not os.path.exists(index_path):
        pytest.skip("FAISS index empty — register faces from test video before this test")

    camera_id = os.environ.get("TEST_CAMERA_ID", "CAM-01")
    rtmp_cam = os.environ.get("TEST_RTMP_CAMERA_ID", "cam01")
    rtsp_host = os.environ.get("MEDIAMTX_HOST", "127.0.0.1")
    rtsp_url = f"rtsp://{rtsp_host}:8554/{rtmp_cam}"
    video = test_video_path()

    length_before = redis_sync.get_stream_length()

    with start_rtmp_simulator(video, camera_id=rtmp_cam, host=rtsp_host):
        time.sleep(3)
        with start_camera_worker(camera_id=camera_id, rtsp_url=rtsp_url):
            def _new_valid_event() -> bool:
                events = redis_sync.read_activity_events(count=50)
                for event in events:
                    if redis_sync.get_stream_length() <= length_before:
                        continue
                    try:
                        redis_sync.validate_activity_event(event)
                    except AssertionError:
                        continue
                    if event.get("camera_id") == camera_id and event.get("participant_id"):
                        return True
                return False

            assert wait_for(_new_valid_event, timeout_seconds=120, description="activity_stream event"), (
                f"XLEN={redis_sync.get_stream_length()}, status={redis_sync.get_camera_status(camera_id)}"
            )

            events = redis_sync.read_activity_events(count=50)
            valid = [e for e in events if e.get("camera_id") == camera_id and e.get("participant_id")]
            assert valid, "No identified events for camera"
            redis_sync.validate_activity_event(valid[-1])
            assert float(valid[-1]["confidence"]) >= 0.5
