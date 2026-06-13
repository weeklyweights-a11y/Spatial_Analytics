"""Participant CRUD endpoints."""

import uuid
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, get_face_matcher, require_role
from backend.api.schemas import PaginationMeta, ParticipantResponse
from backend.db.database import get_db
from backend.db.models import Participant, Score

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


@router.get("/{participant_id}")
async def get_participant(
    participant_id: uuid.UUID,
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


@router.delete("/{participant_id}")
async def delete_participant(
    participant_id: uuid.UUID,
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
