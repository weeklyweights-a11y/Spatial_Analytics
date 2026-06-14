"""Integration tests for sponsor report endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from backend.db.models import Sponsor, Zone


@pytest.fixture
def sponsor_id(sync_engine) -> uuid.UUID:
    sid = uuid.uuid4()
    zid = uuid.uuid4()
    with Session(sync_engine) as session:
        session.add(
            Zone(
                id=zid,
                name="Test Booth",
                zone_type="sponsor",
                camera_id="CAM-01",
                polygon_coords={"points": [[0, 0], [1, 0], [1, 1]]},
                floor=0,
            )
        )
        session.flush()
        session.add(Sponsor(id=sid, name="Test Sponsor", tier="gold", booth_zone_id=zid))
        session.commit()
    return sid


@pytest.mark.asyncio
async def test_sponsor_report_json(client: AsyncClient, admin_token: str, sponsor_id: uuid.UUID) -> None:
    res = await client.get(
        f"/api/v1/sponsors/{sponsor_id}/report",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["sponsor"]["name"] == "Test Sponsor"
    assert "unique_visitors" in data["metrics"]
    assert "by_track" in data["visitor_breakdown"]
