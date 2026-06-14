"""Integration tests for sponsor pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from backend.core.sponsor_processor import process_sponsor_events
from backend.db.models import Participant, ParticipantSponsorVisit, Sponsor, SponsorEngagement, Zone
from backend.db.sync_database import sync_session


@pytest.fixture
def sponsor_setup(sync_engine) -> dict:
    sponsor_id = uuid.uuid4()
    zone_id = uuid.uuid4()
    participant_ids = [uuid.uuid4() for _ in range(3)]
    with Session(sync_engine) as session:
        session.add(
            Zone(
                id=zone_id,
                name="Lovable Booth",
                zone_type="sponsor",
                camera_id="CAM-01",
                polygon_coords={"points": [[0, 0], [1, 0], [1, 1]]},
                floor=0,
            )
        )
        session.flush()
        session.add(
            Sponsor(
                id=sponsor_id,
                name="Lovable",
                tier="gold",
                booth_zone_id=zone_id,
            )
        )
        for i, pid in enumerate(participant_ids):
            session.add(
                Participant(
                    id=pid,
                    name=f"User {i}",
                    team_name=f"Team {i}",
                    track="ai_ml",
                )
            )
        session.commit()
    return {"sponsor_id": sponsor_id, "participant_ids": participant_ids}


def test_sponsor_stream_aggregation(sponsor_setup) -> None:
    sponsor_id = sponsor_setup["sponsor_id"]
    pids = sponsor_setup["participant_ids"]
    base = datetime(2026, 6, 13, 14, 0, tzinfo=timezone.utc)

    events = []
    for i, pid in enumerate(pids):
        t_in = base.replace(minute=i * 2)
        t_out = base.replace(minute=i * 2 + 1)
        events.append(
            {
                "type": "sponsor_entry",
                "participant_id": str(pid),
                "sponsor_id": str(sponsor_id),
                "sponsor_name": "Lovable",
                "camera_id": "CAM-01",
                "timestamp": t_in.isoformat(),
            }
        )
        events.append(
            {
                "type": "sponsor_exit",
                "participant_id": str(pid),
                "sponsor_id": str(sponsor_id),
                "sponsor_name": "Lovable",
                "camera_id": "CAM-01",
                "timestamp": t_out.isoformat(),
            }
        )

    with sync_session() as session:
        process_sponsor_events(session, events)
        from sqlalchemy import select

        visits = session.execute(
            select(ParticipantSponsorVisit).where(ParticipantSponsorVisit.sponsor_id == sponsor_id)
        ).scalars().all()
        assert len(visits) == 3
        assert all(v.exited_at is not None for v in visits)
        engagement = session.execute(
            select(SponsorEngagement).where(SponsorEngagement.sponsor_id == sponsor_id)
        ).scalars().all()
        assert len(engagement) >= 1
        assert engagement[0].unique_visitors == 3
