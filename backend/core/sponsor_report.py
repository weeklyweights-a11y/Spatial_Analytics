"""Build sponsor report JSON and PDF helper data."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.sponsor_aggregation import (
    build_hourly_traffic,
    build_team_size_breakdown,
    build_visitor_breakdown,
    compute_report_metrics,
)
from backend.db.models import Participant, ParticipantSponsorVisit, Sponsor, SponsorEngagement, Zone


async def get_sponsor_or_none(session: AsyncSession, sponsor_id: uuid.UUID) -> Optional[Sponsor]:
    """Load sponsor row."""
    return await session.get(Sponsor, sponsor_id)


async def build_sponsor_report(session: AsyncSession, sponsor_id: uuid.UUID) -> Optional[dict[str, Any]]:
    """Build Section 3 exact JSON report payload."""
    sponsor = await get_sponsor_or_none(session, sponsor_id)
    if sponsor is None:
        return None

    visit_rows = (
        await session.execute(
            select(ParticipantSponsorVisit)
            .where(
                ParticipantSponsorVisit.sponsor_id == sponsor_id,
                ParticipantSponsorVisit.exited_at.isnot(None),
            )
            .order_by(ParticipantSponsorVisit.entered_at)
        )
    ).scalars().all()

    visits_data: list[dict[str, Any]] = []
    participant_ids: set[uuid.UUID] = set()
    for v in visit_rows:
        participant_ids.add(v.participant_id)
        visits_data.append(
            {
                "participant_id": v.participant_id,
                "dwell_seconds": v.dwell_seconds or 0,
                "visits": 1,
                "entered_at": v.entered_at,
            }
        )

    hourly_rows_raw = (
        await session.execute(
            select(SponsorEngagement).where(SponsorEngagement.sponsor_id == sponsor_id)
        )
    ).scalars().all()
    hourly_rows = [
        {
            "hour_bucket": row.hour_bucket,
            "unique_visitors": row.unique_visitors,
            "total_visits": row.total_visits,
        }
        for row in hourly_rows_raw
    ]

    metrics = compute_report_metrics(visits_data, hourly_rows)

    participant_meta: dict[uuid.UUID, dict[str, Any]] = {}
    if participant_ids:
        prows = (
            await session.execute(select(Participant).where(Participant.id.in_(participant_ids)))
        ).scalars().all()
        booth_zone_id = sponsor.booth_zone_id
        floor = 0
        if booth_zone_id:
            zone = await session.get(Zone, booth_zone_id)
            if zone:
                floor = zone.floor
        for p in prows:
            participant_meta[p.id] = {
                "track": p.track,
                "team_name": p.team_name,
                "name": p.name,
                "floor": floor,
            }

    breakdown = build_visitor_breakdown(visits_data, participant_meta)

    dwell_by_participant: dict[uuid.UUID, dict[str, Any]] = {}
    visit_count: dict[uuid.UUID, int] = {}
    for v in visit_rows:
        pid = v.participant_id
        visit_count[pid] = visit_count.get(pid, 0) + 1
        entry = dwell_by_participant.setdefault(
            pid,
            {"participant_id": pid, "visits": 0, "total_dwell_minutes": 0},
        )
        entry["visits"] = visit_count[pid]
        entry["total_dwell_minutes"] += int((v.dwell_seconds or 0) / 60)

    top_visitors: list[dict[str, Any]] = []
    for pid, data in sorted(
        dwell_by_participant.values(),
        key=lambda x: x["total_dwell_minutes"],
        reverse=True,
    )[:10]:
        meta = participant_meta.get(data["participant_id"], {})
        top_visitors.append(
            {
                "participant_id": str(data["participant_id"]),
                "name": meta.get("name", "Unknown"),
                "visits": data["visits"],
                "total_dwell_minutes": data["total_dwell_minutes"],
            }
        )

    booth_name = None
    if sponsor.booth_zone_id:
        zone = await session.get(Zone, sponsor.booth_zone_id)
        booth_name = zone.name if zone else None

    return {
        "sponsor": {
            "id": str(sponsor.id),
            "name": sponsor.name,
            "tier": sponsor.tier,
            "booth_zone": booth_name,
            "logo_url": sponsor.logo_url,
        },
        "metrics": metrics,
        "hourly_traffic": build_hourly_traffic(hourly_rows),
        "visitor_breakdown": breakdown,
        "top_visitors": top_visitors,
    }


async def build_team_size_breakdown_for_pdf(
    session: AsyncSession,
    sponsor_id: uuid.UUID,
) -> dict[str, int]:
    """Team-size pie data for PDF only."""
    visit_rows = (
        await session.execute(
            select(ParticipantSponsorVisit.participant_id)
            .where(
                ParticipantSponsorVisit.sponsor_id == sponsor_id,
                ParticipantSponsorVisit.exited_at.isnot(None),
            )
            .distinct()
        )
    ).all()
    pids = [row[0] for row in visit_rows]
    if not pids:
        return {}
    prows = (await session.execute(select(Participant).where(Participant.id.in_(pids)))).scalars().all()
    meta = {p.id: {"team_name": p.team_name} for p in prows}
    visits_data = [{"participant_id": pid} for pid in pids]
    return build_team_size_breakdown(visits_data, meta)


async def list_sponsors_summary(session: AsyncSession) -> list[dict[str, Any]]:
    """List sponsors with booth zone for dashboard selector."""
    rows = (await session.execute(select(Sponsor).order_by(Sponsor.name))).scalars().all()
    result: list[dict[str, Any]] = []
    for sponsor in rows:
        booth_name = None
        if sponsor.booth_zone_id:
            zone = await session.get(Zone, sponsor.booth_zone_id)
            booth_name = zone.name if zone else None
        unique_visitors = await session.scalar(
            select(func.count(func.distinct(ParticipantSponsorVisit.participant_id))).where(
                ParticipantSponsorVisit.sponsor_id == sponsor.id,
                ParticipantSponsorVisit.exited_at.isnot(None),
            )
        )
        result.append(
            {
                "id": str(sponsor.id),
                "name": sponsor.name,
                "tier": sponsor.tier,
                "booth_zone": booth_name,
                "unique_visitors": int(unique_visitors or 0),
                "logo_url": sponsor.logo_url,
            }
        )
    return result
