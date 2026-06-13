"""Admin metrics endpoint."""

import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, get_face_matcher, require_role
from backend.api.schemas import MetricsResponse
from backend.db.database import get_db, engine
from backend.db.models import Participant
from backend.db.redis_client import get_redis

router = APIRouter(prefix="/api/v1", tags=["metrics"])


@router.get("/metrics")
async def get_metrics(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(["admin"])),
    face_matcher=Depends(get_face_matcher),
) -> dict:
    """Admin-only system metrics."""
    total = await db.scalar(
        select(func.count()).select_from(Participant).where(Participant.opted_out.is_(False))
    )
    redis = await get_redis()
    info = await redis.info("memory")
    uptime = time.time() - request.app.state.start_time

    metrics = MetricsResponse(
        total_registered=total or 0,
        faiss_index_size=face_matcher.count(),
        redis_memory_used_mb=info.get("used_memory", 0) / (1024 * 1024),
        postgres_connection_pool={"pool_size": engine.pool.size()},
        uptime_seconds=uptime,
    )
    return {"data": metrics.model_dump()}
