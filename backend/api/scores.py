"""Score and leaderboard REST endpoints."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.deps import CurrentUser, require_role
from backend.api.schemas import (
    ActivityBreakdown,
    ActivityTimelineHour,
    ActivityTimelineResponse,
    PaginationMeta,
    RadarAxis,
    ScoreDetailResponse,
    ScoreLeaderboardEntry,
    ScoreLeaderboardResponse,
)
from backend.config import get_settings
from backend.core.scoring_engine import build_radar_data
from backend.db.database import get_db
from backend.db.models import ActivityLog, Participant, Score, Zone
from backend.db.redis_client import get_participant_state, get_redis, get_heatmap_current, invalidate_leaderboard_cache, init_redis
from backend.middleware.rate_limit import limiter

settings = get_settings()

LEADERBOARD_CACHE_TTL = 30
BREAKDOWN_COLUMNS = [
    ("coding", "coding_minutes"),
    ("collaborating", "collaborating_minutes"),
    ("mentoring", "mentoring_minutes"),
    ("presenting", "presenting_minutes"),
    ("networking", "networking_minutes"),
    ("helping", "helping_minutes"),
    ("idle", "idle_minutes"),
]


def _sort_column(sort_by: str):
    """Map API sort_by to Score column."""
    if sort_by == "total_score":
        return Score.total_score
    col_name = f"{sort_by}_minutes" if not sort_by.endswith("_minutes") else sort_by
    return getattr(Score, col_name, Score.total_score)


router = APIRouter(prefix="/api/v1", tags=["scores"])


def _photo_base64(participant: Participant) -> Optional[str]:
    if not participant.photo_path:
        return None
    path = Path(participant.photo_path)
    if not path.is_absolute():
        path = Path("/app") / participant.photo_path.lstrip("/")
    if not path.exists():
        faces = Path("/app/data/faces") / f"{participant.id}.jpg"
        path = faces if faces.exists() else path
    if not path.exists():
        return None
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{data}"


@router.get("/scores/leaderboard")
async def get_leaderboard(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin", "operator", "viewer"])),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort_by: str = Query("total_score"),
    sort_order: str = Query("desc"),
    tag: Optional[str] = Query(None),
    track: Optional[str] = Query(None),
    team: Optional[str] = Query(None),
    floor: Optional[int] = Query(None),
) -> dict:
    """Paginated leaderboard with live Redis state."""
    cache_key = (
        f"leaderboard_cache:{sort_by}:{sort_order}:{page}:{per_page}:"
        f"{tag or ''}:{track or ''}:{team or ''}:{floor if floor is not None else ''}"
    )
    redis = await get_redis()
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    count_stmt = select(func.count()).select_from(Participant).where(Participant.opted_out.is_(False))
    if track:
        count_stmt = count_stmt.where(Participant.track == track)
    if team:
        count_stmt = count_stmt.where(Participant.team_name.ilike(f"%{team}%"))
    total_participants = await db.scalar(count_stmt)

    sort_col = _sort_column(sort_by)
    stmt = (
        select(Participant, Score)
        .join(Score, Score.participant_id == Participant.id, isouter=True)
        .where(Participant.opted_out.is_(False))
    )
    if track:
        stmt = stmt.where(Participant.track == track)
    if team:
        stmt = stmt.where(Participant.team_name.ilike(f"%{team}%"))
    if tag:
        stmt = stmt.where(Score.tags.any(tag.title()))
    if floor is not None:
        stmt = stmt.join(Zone, Zone.name == Score.last_zone).where(Zone.floor == floor)
    if sort_order == "asc":
        stmt = stmt.order_by(sort_col.asc().nulls_last())
    else:
        stmt = stmt.order_by(sort_col.desc().nulls_last())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(stmt)).all()

    entries: list[ScoreLeaderboardEntry] = []
    for participant, score in rows:
        state = await get_participant_state(str(participant.id))
        entries.append(
            ScoreLeaderboardEntry(
                participant_id=participant.id,
                name=participant.name,
                team_name=participant.team_name,
                track=participant.track,
                total_score=float(score.total_score if score else 0),
                rank=score.rank if score else None,
                current_activity=state.get("activity") or (score.last_activity if score else None),
                current_zone=state.get("zone") or (score.last_zone if score else None),
                tags=list(score.tags or []) if score else [],
            )
        )

    response = {
        "data": [e.model_dump(mode="json") for e in entries],
        "pagination": PaginationMeta(page=page, per_page=per_page, total=total_participants or 0).model_dump(),
        "total_participants": total_participants or 0,
    }
    await redis.setex(cache_key, LEADERBOARD_CACHE_TTL, json.dumps(response, default=str))
    return response


@router.get("/scores/compare")
@limiter.limit("30/minute")
async def compare_scores(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin", "operator", "viewer"])),
    ids: str = Query(..., description="Comma-separated participant UUIDs"),
) -> dict:
    """Side-by-side score comparison for 2-5 participants."""
    id_list = [UUID(x.strip()) for x in ids.split(",") if x.strip()]
    if len(id_list) < 2 or len(id_list) > 5:
        raise HTTPException(
            status_code=400,
            detail={"error": "Provide 2 to 5 participant IDs", "code": "INVALID_COMPARE"},
        )
    participants_out = []
    for pid in id_list:
        stmt = select(Participant).options(selectinload(Participant.score)).where(Participant.id == pid)
        participant = (await db.execute(stmt)).scalar_one_or_none()
        if participant is None:
            raise HTTPException(status_code=404, detail={"error": "Participant not found", "code": "NOT_FOUND"})
        score = participant.score
        minutes_dict: dict[str, float] = {}
        breakdown: dict[str, ActivityBreakdown] = {}
        total_minutes = 0.0
        if score:
            for label, col in BREAKDOWN_COLUMNS:
                mins = float(getattr(score, col, 0) or 0)
                minutes_dict[label] = mins
                total_minutes += mins
            for label, col in BREAKDOWN_COLUMNS:
                mins = float(getattr(score, col, 0) or 0)
                pct = (mins / total_minutes * 100) if total_minutes > 0 else 0.0
                breakdown[label] = ActivityBreakdown(
                    minutes=mins,
                    points=mins,
                    percentage=pct,
                )
        radar = [RadarAxis(**r) for r in build_radar_data(minutes_dict)]
        participants_out.append(
            {
                "id": str(participant.id),
                "name": participant.name,
                "team_name": participant.team_name,
                "track": participant.track,
                "total_score": float(score.total_score if score else 0),
                "rank": score.rank if score else None,
                "tags": list(score.tags or []) if score else [],
                "radar_data": [r.model_dump() for r in radar],
                "breakdown": {k: v.model_dump() for k, v in breakdown.items()},
            }
        )
    return {"data": {"participants": participants_out}}


@router.get("/scores/{participant_id}")
async def get_score_detail(
    participant_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
) -> dict:
    """Full score breakdown for score card (admin/operator only)."""
    stmt = (
        select(Participant)
        .options(selectinload(Participant.score))
        .where(Participant.id == participant_id)
    )
    participant = (await db.execute(stmt)).scalar_one_or_none()
    if participant is None:
        raise HTTPException(status_code=404, detail={"error": "Participant not found", "code": "NOT_FOUND"})

    score = participant.score
    state = await get_participant_state(str(participant_id))
    minutes_dict = {}
    breakdown: dict[str, ActivityBreakdown] = {}
    total_minutes = 0.0
    if score:
        for label, col in BREAKDOWN_COLUMNS:
            mins = float(getattr(score, col, 0) or 0)
            minutes_dict[label] = mins
            total_minutes += mins
        weights = {label: 1.0 for label, _ in BREAKDOWN_COLUMNS}
        for label, col in BREAKDOWN_COLUMNS:
            mins = float(getattr(score, col, 0) or 0)
            pct = (mins / total_minutes * 100) if total_minutes > 0 else 0.0
            breakdown[label] = ActivityBreakdown(
                minutes=mins,
                points=mins * weights.get(label, 1.0),
                percentage=pct,
            )

    radar = [RadarAxis(**r) for r in build_radar_data(minutes_dict)]
    detail = ScoreDetailResponse(
        participant_id=participant.id,
        name=participant.name,
        team_name=participant.team_name,
        track=participant.track,
        total_score=float(score.total_score if score else 0),
        rank=score.rank if score else None,
        tags=list(score.tags or []) if score else [],
        current_zone=state.get("zone") or (score.last_zone if score else None),
        current_activity=state.get("activity") or (score.last_activity if score else None),
        photo_base64=_photo_base64(participant),
        radar_data=radar,
        breakdown=breakdown,
        registered_at=participant.registered_at,
        last_seen_at=score.last_seen_at if score else None,
    )
    return {"data": detail.model_dump(mode="json")}


@router.get("/scores/{participant_id}/timeline")
async def get_score_timeline(
    participant_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
) -> dict:
    """Hour-by-hour activity rollup."""
    hour_bucket = func.date_trunc("hour", ActivityLog.timestamp).label("hour")
    stmt = (
        select(
            hour_bucket,
            ActivityLog.activity,
            ActivityLog.zone_id,
            func.count().label("cnt"),
        )
        .where(ActivityLog.participant_id == participant_id)
        .group_by(hour_bucket, ActivityLog.activity, ActivityLog.zone_id)
        .order_by(hour_bucket.desc())
        .limit(48)
    )
    rows = (await db.execute(stmt)).all()
    zone_ids = {r.zone_id for r in rows}
    zone_map: dict[UUID, str] = {}
    if zone_ids:
        zrows = await db.execute(select(Zone.id, Zone.name).where(Zone.id.in_(zone_ids)))
        zone_map = {zid: name for zid, name in zrows.all()}

    timeline: list[ActivityTimelineHour] = []
    by_hour: dict[str, dict] = {}
    for row in rows:
        hour_dt: datetime = row.hour
        hour_key = hour_dt.astimezone(timezone.utc).strftime("%H:00")
        if hour_key not in by_hour or row.cnt > by_hour[hour_key]["cnt"]:
            by_hour[hour_key] = {
                "zone": zone_map.get(row.zone_id, "unknown"),
                "activity": row.activity,
                "minutes": float(row.cnt),
                "cnt": row.cnt,
            }
    for hour_key, data in sorted(by_hour.items()):
        timeline.append(
            ActivityTimelineHour(
                hour=hour_key,
                zone=data["zone"],
                primary_activity=data["activity"],
                minutes=data["minutes"],
            )
        )
    return {"data": ActivityTimelineResponse(timeline=timeline).model_dump(mode="json")}
