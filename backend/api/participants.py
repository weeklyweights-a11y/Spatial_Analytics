"""Participant CRUD endpoints."""

from datetime import timezone
from pathlib import Path
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, get_face_matcher, require_role
from backend.api.schemas import PaginationMeta, ParticipantResponse
from backend.core.sponsor_aggregation import floor_key
from backend.db.database import get_db
from backend.db.models import ActivityLog, Participant, ParticipantSponsorVisit, Score, Sponsor, Zone

router = APIRouter(prefix="/api/v1/participants", tags=["participants"])


@router.get("")
async def list_participants(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    team: Optional[str] = None,
    track: Optional[str] = None,
    count_only: bool = Query(False),
) -> dict:
    """Paginated participant list with optional filters."""
    query = select(Participant).where(Participant.opted_out.is_(False))
    if search:
        query = query.where(
            or_(Participant.name.ilike(f"%{search}%"), Participant.team_name.ilike(f"%{search}%"))
        )
    if team:
        query = query.where(Participant.team_name.ilike(f"%{team}%"))
    if track:
        query = query.where(Participant.track == track)

    if count_only:
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        return {"data": {"count": total or 0}}

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(Participant.registered_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    participants = result.scalars().all()
    items = [ParticipantResponse.model_validate(p).model_dump() for p in participants]
    return {
        "data": items,
        "pagination": PaginationMeta(page=page, per_page=per_page, total=total or 0).model_dump(),
    }


@router.get("/{participant_id}/sponsor-visits")
async def get_participant_sponsor_visits(
    participant_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
) -> dict:
    """Sponsor booth visits for participant profile."""
    exists = await db.get(Participant, participant_id)
    if exists is None or exists.opted_out:
        raise HTTPException(status_code=404, detail={"error": "Participant not found", "code": "NOT_FOUND"})

    rows = (
        await db.execute(
            select(ParticipantSponsorVisit, Sponsor.name)
            .join(Sponsor, Sponsor.id == ParticipantSponsorVisit.sponsor_id)
            .where(ParticipantSponsorVisit.participant_id == participant_id)
            .order_by(ParticipantSponsorVisit.entered_at)
        )
    ).all()
    visits = [
        {
            "sponsor_name": name,
            "visit_number": visit.visit_number,
            "entered_at": visit.entered_at.isoformat(),
            "exited_at": visit.exited_at.isoformat() if visit.exited_at else None,
            "dwell_seconds": visit.dwell_seconds,
        }
        for visit, name in rows
    ]
    return {"data": visits}


@router.get("/{participant_id}/zone-history")
async def get_participant_zone_history(
    participant_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
) -> dict:
    """Zone visit history grouped by zone with floor totals."""
    exists = await db.get(Participant, participant_id)
    if exists is None or exists.opted_out:
        raise HTTPException(status_code=404, detail={"error": "Participant not found", "code": "NOT_FOUND"})

    rows = (
        await db.execute(
            select(
                Zone.name,
                Zone.zone_type,
                Zone.floor,
                func.count().label("events"),
            )
            .join(ActivityLog, ActivityLog.zone_id == Zone.id)
            .where(ActivityLog.participant_id == participant_id)
            .group_by(Zone.name, Zone.zone_type, Zone.floor)
            .order_by(Zone.name)
        )
    ).all()

    zones: list[dict] = []
    floor_minutes: dict[str, float] = {"ground": 0.0, "first": 0.0, "second": 0.0}
    coding_zones: set[str] = set()
    for name, zone_type, floor, events in rows:
        minutes = float(events) / 6.0
        zones.append({"zone": name, "zone_type": zone_type, "minutes": round(minutes, 1)})
        fk = floor_key(int(floor))
        if fk in floor_minutes:
            floor_minutes[fk] += minutes
        if zone_type == "coding":
            coding_zones.add(name)

    return {
        "data": {
            "zones": zones,
            "floor_totals_hours": {k: round(v / 60.0, 1) for k, v in floor_minutes.items()},
            "distinct_coding_zones_visited": len(coding_zones),
        }
    }


@router.get("/{participant_id}")
async def get_participant(
    participant_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
) -> dict:
    """Single participant with score data."""
    result = await db.execute(
        select(Participant, Score)
        .outerjoin(Score, Score.participant_id == Participant.id)
        .where(Participant.id == participant_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "Participant not found", "code": "NOT_FOUND"})
    participant, score = row
    data = ParticipantResponse.model_validate(participant).model_dump()
    if score:
        data["total_score"] = score.total_score
    return {"data": data}


@router.get("/{participant_id}/photo")
async def get_participant_photo(
    participant_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
) -> FileResponse:
    """Serve registration photo file."""
    result = await db.execute(select(Participant).where(Participant.id == participant_id))
    participant = result.scalar_one_or_none()
    if participant is None or participant.opted_out:
        raise HTTPException(status_code=404, detail={"error": "Participant not found", "code": "NOT_FOUND"})
    path = Path(participant.photo_path) if participant.photo_path else Path(f"/app/data/faces/{participant_id}.jpg")
    if not path.exists():
        alt = Path("/app/data/faces") / f"{participant_id}.jpg"
        path = alt if alt.exists() else path
    if not path.exists():
        raise HTTPException(status_code=404, detail={"error": "Photo not found", "code": "NOT_FOUND"})
    return FileResponse(path, media_type="image/jpeg")


@router.delete("/{participant_id}")
async def delete_participant(
    participant_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin"])),
    face_matcher=Depends(get_face_matcher),
) -> dict:
    """Opt-out: remove embedding, anonymize record, delete photo."""
    result = await db.execute(select(Participant).where(Participant.id == participant_id))
    participant = result.scalar_one_or_none()
    if participant is None:
        raise HTTPException(status_code=404, detail={"error": "Participant not found", "code": "NOT_FOUND"})

    if participant.embedding_id is not None:
        face_matcher.remove_by_index(participant.embedding_id)
        try:
            face_matcher.save()
        except Exception as exc:
            from loguru import logger

            logger.error("FAISS index save failed: {error}", error=str(exc))

    if participant.photo_path:
        path = Path(participant.photo_path)
        if path.exists():
            path.unlink()

    participant.name = "Opted Out"
    participant.email = None
    participant.team_name = "Removed"
    participant.skills = []
    participant.photo_path = None
    participant.embedding_id = None
    participant.opted_out = True

    return {"data": {"id": str(participant_id), "opted_out": True}}
