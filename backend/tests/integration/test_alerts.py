"""Integration tests for alert persistence and REST."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.core.alert_engine import evaluate_alerts
from backend.db import redis_sync
from backend.db.models import Alert, Zone
from backend.db.sync_database import insert_alert, load_zone_metadata, sync_session
from backend.tests.integration.pipeline_helpers import redis_available


@pytest.fixture
def require_redis():
    if not redis_available():
        pytest.skip("Redis not reachable at REDIS_URL")


@pytest.mark.asyncio
async def test_capacity_alert_persisted_and_listed(app, admin_token, sync_engine, require_redis):
    """Force 95% occupancy and verify alert in DB + REST."""
    zone_name = "Alert Test Zone"
    with Session(sync_engine) as session:
        session.execute(text("DELETE FROM alerts"))
        existing = session.execute(select(Zone).where(Zone.name == zone_name)).scalar_one_or_none()
        if existing is None:
            import uuid

            session.add(
                Zone(
                    id=uuid.uuid4(),
                    name=zone_name,
                    zone_type="coding",
                    camera_id="CAM-01",
                    polygon_coords={"points": [[0, 0], [1, 0], [1, 1]]},
                    floor=0,
                    capacity=20,
                )
            )
        else:
            existing.capacity = 20
        session.commit()

    redis_sync.update_zone_occupancy(zone_name, 19)

    with sync_session() as session:
        meta = load_zone_metadata(session)

    snap = {
        "zones": {zone_name: {"count": 19, "capacity": 20, "pct": 95, "floor": 0}},
        "energy_level": 0.5,
        "total_active": 100,
        "total_registered": 1000,
    }

    with patch("backend.core.alert_engine.redis_sync.get_alert_cooldown", return_value=None):
        with patch("backend.core.alert_engine.redis_sync.set_alert_cooldown"):
            alerts = evaluate_alerts(snap, meta)

    assert any(a["rule_name"] == "zone_capacity" for a in alerts)
    fired = datetime.now(timezone.utc)
    with sync_session() as session:
        for alert in alerts:
            insert_alert(
                session,
                rule_name=alert["rule_name"],
                severity=alert["severity"],
                message=alert["message"],
                zone=alert.get("zone"),
                floor=alert.get("floor"),
                fired_at=fired,
            )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/alerts",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert res.status_code == 200
    data = res.json()["data"]
    assert any(row["rule_name"] == "zone_capacity" for row in data)

    with Session(sync_engine) as session:
        count = session.execute(select(func.count()).select_from(Alert)).scalar()
    assert count and count >= 1
