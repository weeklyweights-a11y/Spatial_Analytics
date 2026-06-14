"""Health check endpoint."""

import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.schemas import CameraHealthStatus, HealthCheckDetail, HealthResponse
from backend.config import get_settings
from backend.db.database import get_db, engine
from backend.db.redis_client import get_camera_statuses, get_redis
from backend.db.redis_sync import get_heatmap_status, get_scoring_last_flush_at, get_scoring_status
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

    camera_statuses: list[CameraHealthStatus] = []
    try:
        statuses = await get_camera_statuses()
        now = time.time()
        for cam_id, fields in statuses.items():
            last_hb = fields.get("last_heartbeat", "")
            stale = False
            if last_hb:
                try:
                    from datetime import datetime, timezone

                    hb_dt = datetime.fromisoformat(last_hb.replace("Z", "+00:00"))
                    age = (datetime.now(timezone.utc) - hb_dt).total_seconds()
                    stale = age > 30
                except ValueError:
                    stale = True
            cam_status = fields.get("status", "unknown")
            if stale and cam_status == "active":
                cam_status = "stale"
            camera_statuses.append(
                CameraHealthStatus(
                    camera_id=cam_id,
                    status=cam_status,
                    fps=float(fields["fps"]) if fields.get("fps") else None,
                    persons_tracked=int(fields["persons_tracked"]) if fields.get("persons_tracked") else None,
                    stale=stale,
                )
            )
            if stale:
                all_ok = False
        checks["cameras"] = HealthCheckDetail(status="ok" if not any(c.stale for c in camera_statuses) else "degraded")
    except Exception as exc:
        checks["cameras"] = HealthCheckDetail(status="error", detail=str(exc))

    try:
        flush_at = get_scoring_last_flush_at()
        status_fields = get_scoring_status()
        worker_status = status_fields.get("status", "unknown")
        lag_ok = True
        detail_parts = [f"worker={worker_status}"]
        if flush_at:
            from datetime import datetime, timezone

            flush_dt = datetime.fromisoformat(flush_at.replace("Z", "+00:00"))
            lag = (datetime.now(timezone.utc) - flush_dt).total_seconds()
            detail_parts.append(f"lag={lag:.0f}s")
            lag_ok = lag < settings.SCORING_FLUSH_INTERVAL * 2
        scoring_ok = worker_status == "running" and lag_ok
        checks["scoring_engine"] = HealthCheckDetail(
            status="ok" if scoring_ok else "degraded",
            detail=", ".join(detail_parts),
        )
        if not scoring_ok:
            all_ok = False
    except Exception as exc:
        checks["scoring_engine"] = HealthCheckDetail(status="error", detail=str(exc))
        all_ok = False

    try:
        hm = get_heatmap_status()
        last_hb = hm.get("last_heartbeat", "")
        stale = True
        if last_hb:
            from datetime import datetime, timezone

            hb_dt = datetime.fromisoformat(last_hb.replace("Z", "+00:00"))
            stale = (datetime.now(timezone.utc) - hb_dt).total_seconds() > 30
        hm_status = hm.get("status", "unknown")
        checks["heatmap_worker"] = HealthCheckDetail(
            status="ok" if not stale and hm_status == "running" else "degraded",
            detail=f"status={hm_status}, stale={stale}",
        )
        if stale:
            all_ok = False
    except Exception as exc:
        checks["heatmap_worker"] = HealthCheckDetail(status="error", detail=str(exc))

    status_str = "healthy" if all_ok else "degraded"
    if any(c.status == "error" for c in checks.values()):
        status_str = "unhealthy"

    uptime = time.time() - request.app.state.start_time
    return HealthResponse(status=status_str, checks=checks, uptime_seconds=uptime, cameras=camera_statuses)
