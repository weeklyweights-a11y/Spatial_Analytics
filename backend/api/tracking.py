"""Live tracking REST endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends

from backend.api.deps import CurrentUser, require_role
from backend.api.schemas import ActiveParticipant
from backend.db.redis_client import get_redis

router = APIRouter(prefix="/api/v1", tags=["tracking"])


@router.get("/tracking/active")
async def get_active_participants(
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
) -> dict:
    """Participants seen within the last 5 minutes."""
    redis = await get_redis()
    now = datetime.now(timezone.utc)
    active: list[ActiveParticipant] = []
    async for key in redis.scan_iter(match="participant:*"):
        fields = await redis.hgetall(key)
        last_seen_raw = fields.get("last_seen")
        if not last_seen_raw:
            continue
        try:
            last_seen = datetime.fromisoformat(last_seen_raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        age = (now - last_seen.astimezone(timezone.utc)).total_seconds()
        if age > 300:
            continue
        pid = key.split(":", 1)[-1]
        active.append(
            ActiveParticipant(
                participant_id=pid,
                zone=fields.get("zone", ""),
                activity=fields.get("activity", ""),
                score=float(fields.get("score", 0) or 0),
                last_seen=last_seen_raw,
            )
        )
    return {"data": [a.model_dump() for a in active]}
