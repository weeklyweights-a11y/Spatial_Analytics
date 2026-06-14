"""Integration tests for export endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from backend.api.deps import create_access_token
from backend.db.models import Participant, Score


@pytest.fixture
def operator_token():
    from datetime import datetime, timedelta, timezone

    return create_access_token("testoperator", "operator", datetime.now(timezone.utc) + timedelta(hours=1))


@pytest.fixture
def viewer_token():
    from datetime import datetime, timedelta, timezone

    return create_access_token("testviewer", "viewer", datetime.now(timezone.utc) + timedelta(hours=1))


@pytest.fixture
def seeded_scores(sync_engine):
    with Session(sync_engine) as session:
        for i in range(3):
            pid = uuid.uuid4()
            session.add(
                Participant(
                    id=pid,
                    name=f"P{i}",
                    team_name=f"T{i}",
                    track="ai_ml",
                )
            )
            session.add(Score(participant_id=pid, total_score=float(i * 10)))
        session.commit()


@pytest.mark.asyncio
async def test_export_scores_csv(client: AsyncClient, admin_token: str, seeded_scores) -> None:
    res = await client.get(
        "/api/v1/export/scores",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert "participant_id" in res.text
    assert res.text.count("\n") >= 4


@pytest.mark.asyncio
async def test_export_operator_forbidden(client: AsyncClient, operator_token: str) -> None:
    res = await client.get(
        "/api/v1/export/scores",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_export_viewer_forbidden(client: AsyncClient, viewer_token: str) -> None:
    res = await client.get(
        "/api/v1/export/scores",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_trajectory_anonymized(client: AsyncClient, admin_token: str) -> None:
    res = await client.get(
        "/api/v1/export/trajectories?format=opentraj&anonymize=true",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    assert "frame_id" in res.text
