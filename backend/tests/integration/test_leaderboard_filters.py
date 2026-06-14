"""Integration tests for leaderboard filters and compare."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from backend.db.models import Participant, Score, Zone


@pytest.mark.asyncio
async def test_leaderboard_track_filter(app, admin_token, sync_engine):
    pid_ai = uuid.uuid4()
    pid_web = uuid.uuid4()
    with Session(sync_engine) as session:
        session.add(Participant(id=pid_ai, name="AI Dev", team_name="Alpha", track="ai_ml"))
        session.add(Participant(id=pid_web, name="Web Dev", team_name="Beta", track="web"))
        session.add(Score(participant_id=pid_ai, total_score=200.0, rank=1))
        session.add(Score(participant_id=pid_web, total_score=150.0, rank=2))
        session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/scores/leaderboard?track=ai_ml",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert res.status_code == 200
    names = [e["name"] for e in res.json()["data"]]
    assert names == ["AI Dev"]


@pytest.mark.asyncio
async def test_leaderboard_floor_filter(app, admin_token, sync_engine):
    pid = uuid.uuid4()
    zone_id = uuid.uuid4()
    with Session(sync_engine) as session:
        session.add(Zone(id=zone_id, name="Floor1 Zone", zone_type="coding", camera_id="CAM-01", polygon_coords={"points": [[0, 0]]}, floor=1, capacity=50))
        session.add(Participant(id=pid, name="Floor One", team_name="T", track="ai_ml"))
        session.add(Score(participant_id=pid, total_score=100.0, rank=1, last_zone="Floor1 Zone"))
        session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/scores/leaderboard?floor=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert res.status_code == 200
    assert len(res.json()["data"]) == 1


@pytest.mark.asyncio
async def test_compare_scores(app, admin_token, sync_engine):
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    with Session(sync_engine) as session:
        session.add(Participant(id=p1, name="A", team_name="T1", track="ai_ml"))
        session.add(Participant(id=p2, name="B", team_name="T2", track="web"))
        session.add(Score(participant_id=p1, total_score=80.0, rank=2))
        session.add(Score(participant_id=p2, total_score=120.0, rank=1))
        session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/scores/compare?ids={p1},{p2}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert res.status_code == 200
    data = res.json()["data"]["participants"]
    assert len(data) == 2
    assert {d["name"] for d in data} == {"A", "B"}
