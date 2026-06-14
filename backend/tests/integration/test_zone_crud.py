"""Integration tests for zone CRUD REST."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from backend.db.models import ActivityLog, Zone
from backend.db.partitions import ensure_activity_log_partition
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_zone_crud_fresh_zone(app, admin_token, sync_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post(
            "/api/v1/zones",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "CRUD Test Zone",
                "zone_type": "coding",
                "camera_id": "CAM-99",
                "polygon_coords": [[0, 0], [100, 0], [100, 100]],
                "floor": 0,
                "capacity": 30,
            },
        )
        assert create.status_code == 200
        zone_id = create.json()["data"]["id"]

        update = await client.put(
            f"/api/v1/zones/{zone_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"capacity": 40},
        )
        assert update.status_code == 200
        assert update.json()["data"]["capacity"] == 40

        delete = await client.delete(
            f"/api/v1/zones/{zone_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert delete.status_code == 200


@pytest.mark.asyncio
async def test_zone_delete_with_logs_returns_409(app, admin_token, sync_engine):
    zone_id = uuid.uuid4()
    participant_id = uuid.uuid4()
    with Session(sync_engine) as session:
        from backend.db.models import Participant

        session.add(
            Zone(
                id=zone_id,
                name="Logged Zone",
                zone_type="coding",
                camera_id="CAM-01",
                polygon_coords={"points": [[0, 0]]},
                floor=0,
                capacity=10,
            )
        )
        session.add(Participant(id=participant_id, name="P", team_name="T", track="ai_ml"))
        session.commit()

    ensure_activity_log_partition(sync_engine, datetime.now(timezone.utc))
    with Session(sync_engine) as session:
        session.add(
            ActivityLog(
                participant_id=participant_id,
                camera_id="CAM-01",
                zone_id=zone_id,
                activity="coding",
                timestamp=datetime.now(timezone.utc),
            )
        )
        session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.delete(
            f"/api/v1/zones/{zone_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert res.status_code == 409
