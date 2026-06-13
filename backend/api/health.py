"""Health check endpoint."""

import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import HealthCheckDetail, HealthResponse
from backend.config import get_settings
from backend.db.database import get_db, engine
from backend.db.redis_client import get_redis
from backend.middleware.rate_limit import limiter

settings = get_settings()
router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
@limiter.exempt
async def health_check(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HealthResponse:
    """No-auth health check for all dependencies."""
    checks: dict[str, HealthCheckDetail] = {}
    all_ok = True

    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = HealthCheckDetail(status="ok")
    except Exception as exc:
        checks["postgres"] = HealthCheckDetail(status="error", detail=str(exc))
        all_ok = False

    try:
        redis = await get_redis()
        pong = await redis.ping()
        checks["redis"] = HealthCheckDetail(status="ok" if pong else "error")
    except Exception as exc:
        checks["redis"] = HealthCheckDetail(status="error", detail=str(exc))
        all_ok = False

    try:
        matcher = request.app.state.face_matcher
        n = matcher.count()
        checks["faiss"] = HealthCheckDetail(status="ok", detail=f"ntotal={n}")
    except Exception as exc:
        checks["faiss"] = HealthCheckDetail(status="error", detail=str(exc))
        all_ok = False

    try:
        data_path = Path(settings.EMBEDDING_MAP_PATH).parent.parent
        data_path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(str(data_path))
        free_gb = usage.free / (1024**3)
        disk_ok = free_gb > 1  # relaxed for dev/CI; production VM has >10GB
        checks["disk"] = HealthCheckDetail(
            status="ok" if free_gb > 10 else ("degraded" if disk_ok else "error"),
            detail=f"{free_gb:.1f}GB free",
        )
        if free_gb <= 1:
            all_ok = False
    except Exception as exc:
        checks["disk"] = HealthCheckDetail(status="error", detail=str(exc))
        all_ok = False

    status_str = "healthy" if all_ok else "degraded"
    if any(c.status == "error" for c in checks.values()):
        status_str = "unhealthy"

    uptime = time.time() - request.app.state.start_time
    return HealthResponse(status=status_str, checks=checks, uptime_seconds=uptime)
