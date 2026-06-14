"""Admin metrics endpoint."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, get_face_matcher, require_role
from backend.api.schemas import MetricsResponse
from backend.db.database import get_db, engine
from backend.db.models import Participant
from backend.db.redis_client import get_camera_statuses, get_redis, get_stream_length
from backend.db.redis_sync import get_scoring_last_flush_at

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

    camera_fields = await get_camera_statuses()
    total_persons = 0
    cameras: dict[str, dict] = {}
    for cam_id, fields in camera_fields.items():
        pt = int(fields.get("persons_tracked", 0) or 0)
        total_persons += pt
        cameras[cam_id] = {
            "fps": fields.get("fps"),
            "frames_processed": fields.get("frames_processed"),
            "persons_tracked": pt,
            "faces_detected": fields.get("faces_detected"),
            "status": fields.get("status"),
        }
    events_in_stream = await get_stream_length()
    scoring_lag_seconds = None
    flush_at = get_scoring_last_flush_at()
    if flush_at:
        flush_dt = datetime.fromisoformat(flush_at.replace("Z", "+00:00"))
        scoring_lag_seconds = (datetime.now(timezone.utc) - flush_dt).total_seconds()

    metrics = MetricsResponse(
        total_registered=total or 0,
        faiss_index_size=face_matcher.count(),
        redis_memory_used_mb=info.get("used_memory", 0) / (1024 * 1024),
        postgres_connection_pool={"pool_size": engine.pool.size()},
        uptime_seconds=uptime,
        events_in_stream=events_in_stream,
        total_persons_tracked=total_persons,
        cameras=cameras,
    )
    return {"data": {**metrics.model_dump(), "scoring_lag_seconds": scoring_lag_seconds}}
