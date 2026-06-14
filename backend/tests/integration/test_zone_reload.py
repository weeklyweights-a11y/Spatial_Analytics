"""Integration tests for zone reload via Redis pub/sub."""

from __future__ import annotations

import threading
import time
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from backend.db import redis_sync
from backend.db.models import Zone
from backend.tests.integration.pipeline_helpers import redis_available
from backend.utils.zone_db_loader import load_zones_from_db


@pytest.fixture
def require_redis():
    if not redis_available():
        pytest.skip("Redis not reachable at REDIS_URL")


class _ReloadTracker:
    """Minimal stand-in for camera worker zone reload."""

    def __init__(self, camera_id: str, sync_engine) -> None:
        self.camera_id = camera_id
        self.sync_engine = sync_engine
        self.reload_count = 0
        self._start_listener()

    def _reload(self) -> None:
        with Session(self.sync_engine) as session:
            load_zones_from_db(session, self.camera_id)
        self.reload_count += 1

    def _start_listener(self) -> None:
        def _listen() -> None:
            r = redis_sync.get_sync_redis()
            pubsub = r.pubsub()
            pubsub.subscribe("zones_updated")
            for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                self._reload()

        threading.Thread(target=_listen, daemon=True).start()


@pytest.mark.asyncio
async def test_zones_updated_triggers_reload(app, admin_token, sync_engine, require_redis):
    camera_id = "CAM-RELOAD"
    tracker = _ReloadTracker(camera_id, sync_engine)
    time.sleep(0.3)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/zones",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": f"Reload Zone {uuid.uuid4().hex[:6]}",
                "zone_type": "coding",
                "camera_id": camera_id,
                "polygon_coords": [[0, 0], [10, 0], [10, 10]],
                "floor": 0,
                "capacity": 25,
            },
        )
    assert res.status_code == 200

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if tracker.reload_count >= 1:
            break
        time.sleep(0.2)
    assert tracker.reload_count >= 1
