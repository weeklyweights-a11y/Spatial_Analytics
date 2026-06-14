"""Scoring configuration REST endpoints."""

from __future__ import annotations

from typing import Annotated, List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, require_role
from backend.db.database import get_db
from backend.db.models import ScoringConfig
from backend.db.redis_client import publish_scoring_config_updated
from backend.middleware.rate_limit import limiter

router = APIRouter(prefix="/api/v1", tags=["config"])


class ScoringWeightUpdate(BaseModel):
    """Single activity weight update."""

    activity: str
    weight: float
    min_dwell_seconds: int = 120


class ScoringConfigUpdateRequest(BaseModel):
    """Bulk scoring config update."""

    weights: List[ScoringWeightUpdate]


@router.get("/config/scoring")
async def get_scoring_config(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin"])),
) -> dict:
    """Return all scoring weights."""
    rows = (await db.execute(select(ScoringConfig))).scalars().all()
    return {
        "data": [
            {
                "activity": r.activity,
                "weight": float(r.weight),
                "min_dwell_seconds": int(r.min_dwell_seconds),
                "description": r.description,
            }
            for r in rows
        ]
    }


@router.put("/config/scoring")
@limiter.limit("2/minute")
async def update_scoring_config(
    request: Request,
    body: ScoringConfigUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin"])),
) -> dict:
    """Update scoring weights; scoring worker reloads on next cycle."""
    for item in body.weights:
        row = await db.get(ScoringConfig, item.activity)
        if row is None:
            row = ScoringConfig(activity=item.activity, weight=item.weight, min_dwell_seconds=item.min_dwell_seconds)
            db.add(row)
        else:
            row.weight = item.weight
            row.min_dwell_seconds = item.min_dwell_seconds
    await db.commit()
    await publish_scoring_config_updated()
    rows = (await db.execute(select(ScoringConfig))).scalars().all()
    return {
        "data": [
            {
                "activity": r.activity,
                "weight": float(r.weight),
                "min_dwell_seconds": int(r.min_dwell_seconds),
            }
            for r in rows
        ]
    }
