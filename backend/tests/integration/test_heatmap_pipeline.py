"""Integration tests for heatmap worker cycle and analytics REST."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text

from backend.db import redis_sync
from backend.db.models import HeatmapSnapshot
from backend.tests.integration.pipeline_helpers import redis_available
from backend.workers.heatmap_worker import HeatmapWorker


@pytest.fixture
def require_redis():
    if not redis_available():
        pytest.skip("Redis not reachable at REDIS_URL")


@pytest.mark.asyncio
async def test_heatmap_cycle_inserts_snapshot(app, admin_token, sync_engine, require_redis):
    """Run one heatmap cycle and verify DB row + REST endpoints."""
    with sync_engine.connect() as conn:
        conn.execute(text("DELETE FROM heatmap_snapshots"))
        conn.commit()

    redis_sync.update_zone_occupancy("Coding Zone A", 10)

    worker = HeatmapWorker()
    worker._cycle()

    with sync_engine.connect() as conn:
        count = conn.execute(select(func.count()).select_from(HeatmapSnapshot)).scalar()
    assert count and count >= 1

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        heatmap = await client.get(
            "/api/v1/analytics/heatmap",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        energy = await client.get(
            "/api/v1/analytics/energy",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert heatmap.status_code == 200
    assert "zones" in heatmap.json().get("data", {})
    assert energy.status_code == 200
    assert "points" in energy.json().get("data", {})
