"""Integration tests for identity pipeline (register + camera worker events)."""

from __future__ import annotations

import os
import time
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db import redis_sync
from backend.tests.integration.pipeline_helpers import (
    frame_to_jpeg_bytes,
    gpu_pipeline_enabled,
    gpu_prerequisites_met,
    gpu_skip_reason,
    integration_enabled,
    read_video_frame,
    skip_reason,
    start_camera_worker,
    start_rtmp_simulator,
    test_video_path,
    wait_for,
)

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not integration_enabled(), reason=skip_reason())
@pytest.mark.asyncio
async def test_register_face_from_test_video_frame(live_cv_app, admin_token):
    """Register a participant using a frame extracted from the test video."""
    if not test_video_path().exists():
        pytest.skip(f"Test video not found: {test_video_path()}")

    frame = read_video_frame(test_video_path(), frame_index=0)
    jpeg = frame_to_jpeg_bytes(frame)
    unique = uuid.uuid4().hex[:8]

    transport = ASGITransport(app=live_cv_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/register",
            headers={"Authorization": f"Bearer {admin_token}"},
            data={
                "name": f"Pipeline Test {unique}",
                "team_name": "Pipeline Team",
                "track": "ai_ml",
                "consent_confirmed": "true",
            },
            files={"photo": ("frame.jpg", jpeg, "image/jpeg")},
        )

    if res.status_code == 400 and "No face detected" in res.json().get("error", ""):
        pytest.skip("Test video frame has no detectable face for registration")

    assert res.status_code == 201, res.text
    data = res.json()["data"]
    assert data["embedding_id"] is not None
    assert data["id"]
    live_cv_app.state.face_matcher.save()


@pytest.mark.skipif(not gpu_pipeline_enabled(), reason=gpu_skip_reason())
@pytest.mark.skipif(not gpu_prerequisites_met(), reason="Missing DEIMv2 model, test video, ffmpeg, or Redis")
@pytest.mark.asyncio
async def test_identity_pipeline_emits_registered_participant(live_cv_app, admin_token):
    """Register from test video, run worker, assert activity_stream contains participant_id."""
    redis_sync.close_sync_redis()

    frame = read_video_frame(test_video_path(), frame_index=0)
    jpeg = frame_to_jpeg_bytes(frame)
    unique = uuid.uuid4().hex[:8]
    participant_name = f"E2E User {unique}"

    transport = ASGITransport(app=live_cv_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/register",
            headers={"Authorization": f"Bearer {admin_token}"},
            data={
                "name": participant_name,
                "team_name": "E2E Team",
                "track": "ai_ml",
                "consent_confirmed": "true",
            },
            files={"photo": ("frame.jpg", jpeg, "image/jpeg")},
        )

    if res.status_code == 400 and "No face detected" in res.json().get("error", ""):
        pytest.skip("Test video frame has no detectable face for registration")
    assert res.status_code == 201, res.text
    participant_id = res.json()["data"]["id"]
    live_cv_app.state.face_matcher.save()

    camera_id = os.environ.get("TEST_CAMERA_ID", "CAM-01")
    rtmp_cam = os.environ.get("TEST_RTMP_CAMERA_ID", "cam01")
    rtsp_host = os.environ.get("MEDIAMTX_HOST", "127.0.0.1")
    rtsp_url = f"rtsp://{rtsp_host}:8554/{rtmp_cam}"
    video = test_video_path()

    with start_rtmp_simulator(video, camera_id=rtmp_cam, host=rtsp_host):
        time.sleep(3)
        with start_camera_worker(camera_id=camera_id, rtsp_url=rtsp_url):

            def _event_for_participant() -> bool:
                for event in redis_sync.read_activity_events(count=100):
                    if event.get("participant_id") == participant_id:
                        return True
                return False

            found = wait_for(_event_for_participant, timeout_seconds=120, description="participant event")
            assert found, (
                f"No event for participant_id={participant_id}; "
                f"status={redis_sync.get_camera_status(camera_id)}"
            )

            matching = [
                e
                for e in redis_sync.read_activity_events(count=100)
                if e.get("participant_id") == participant_id
            ]
            assert matching
            event = matching[-1]
            redis_sync.validate_activity_event(event)
            assert event["camera_id"] == camera_id
            assert float(event["confidence"]) >= 0.5
