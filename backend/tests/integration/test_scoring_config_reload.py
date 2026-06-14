"""Integration tests for scoring config reload via Redis pub/sub."""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from backend.tests.integration.pipeline_helpers import redis_available
from backend.workers.scoring_worker import ScoringWorker


@pytest.fixture
def require_redis():
    if not redis_available():
        pytest.skip("Redis not reachable at REDIS_URL")


@pytest.mark.asyncio
async def test_scoring_config_updated_reloads_worker(app, admin_token, require_redis):
    worker = ScoringWorker()
    time.sleep(0.3)
    before = dict(worker._config)
    activity = next(iter(before.keys()))
    new_weight = before[activity].weight + 0.5

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.put(
            "/api/v1/config/scoring",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"weights": [{"activity": activity, "weight": new_weight, "min_dwell_seconds": 120}]},
        )
    assert res.status_code == 200

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        updated = worker._config.get(activity)
        if updated is not None and updated.weight == new_weight:
            break
        time.sleep(0.2)
    assert worker._config[activity].weight == new_weight
