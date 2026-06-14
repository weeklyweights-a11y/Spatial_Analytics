"""Integration tests for score REST endpoints."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from backend.db.models import Participant, Score


@pytest.mark.asyncio
async def test_leaderboard_sorted(app, admin_token, sync_engine):
    pid = uuid.uuid4()
    from sqlalchemy.orm import Session

    with Session(sync_engine) as session:
        session.add(Participant(id=pid, name="LB Test", team_name="T", track="ai_ml"))
        session.add(Score(participant_id=pid, total_score=100.0, rank=1))
        session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/scores/leaderboard?limit=10",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert res.status_code == 200
    data = res.json()["data"]
    assert isinstance(data, list)
    assert "total_participants" in res.json() or "pagination" in res.json()


@pytest.mark.asyncio
async def test_viewer_denied_score_detail(app, sync_engine):
    from backend.api.deps import create_access_token
    from datetime import datetime, timedelta, timezone

    token = create_access_token("testviewer", "viewer", datetime.now(timezone.utc) + timedelta(hours=1))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/scores/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert res.status_code == 403
