"""Analytics REST endpoints — heatmap, energy, zones."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, require_role
from backend.db.database import get_db
from backend.db.models import HeatmapSnapshot
from backend.db.redis_client import get_heatmap_current, get_redis
from backend.middleware.rate_limit import limiter

router = APIRouter(prefix="/api/v1", tags=["analytics"])

ENERGY_CACHE_TTL = 60
ZONES_CACHE_TTL = 60


def _default_time_range() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    return now - timedelta(hours=24), now


@router.get("/analytics/heatmap")
@limiter.limit("30/minute")
async def get_heatmap(
    request: Request,
    user: CurrentUser = Depends(require_role(["admin", "operator", "viewer"])),
) -> dict:
    """Current heatmap snapshot from Redis."""
    snapshot = await get_heatmap_current()
    if snapshot is None:
        return {
            "data": {
                "zones": {},
                "total_active": 0,
                "total_registered": 0,
                "energy_level": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        }
    return {"data": snapshot}


@router.get("/analytics/energy")
@limiter.limit("30/minute")
async def get_energy(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin", "operator", "viewer"])),
    from_ts: Optional[datetime] = Query(None, alias="from"),
    to_ts: Optional[datetime] = Query(None, alias="to"),
    interval: int = Query(30, ge=1, le=1440),
) -> dict:
    """Energy level over time from heatmap_snapshots."""
    start, end = from_ts, to_ts
    if start is None or end is None:
        start, end = _default_time_range()
    cache_key = f"cache:energy:{start.isoformat()}:{end.isoformat()}:{interval}"
    redis = await get_redis()
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    bucket_seconds = interval * 60
    stmt = text(
        """
        SELECT
            to_timestamp(floor(extract(epoch from timestamp) / :bucket) * :bucket) AS bucket_ts,
            AVG(energy_level) AS energy,
            AVG(total_active) AS active
        FROM heatmap_snapshots
        WHERE timestamp >= :start AND timestamp <= :end
        GROUP BY 1
        ORDER BY 1
        """
    )
    rows = (
        await db.execute(
            stmt,
            {"bucket": bucket_seconds, "start": start, "end": end},
        )
    ).all()
    points = [
        {
            "timestamp": row.bucket_ts.astimezone(timezone.utc).isoformat(),
            "energy": round(float(row.energy or 0), 4),
            "active": int(row.active or 0),
        }
        for row in rows
    ]
    response = {
        "data": {
            "points": points,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "interval_minutes": interval,
        }
    }
    await redis.setex(cache_key, ENERGY_CACHE_TTL, json.dumps(response, default=str))
    return response


@router.get("/analytics/zones")
@limiter.limit("30/minute")
async def get_zones_analytics(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin", "operator", "viewer"])),
    from_ts: Optional[datetime] = Query(None, alias="from"),
    to_ts: Optional[datetime] = Query(None, alias="to"),
    floor: Optional[int] = Query(None),
    interval: int = Query(30, ge=1, le=1440),
) -> dict:
    """Per-zone occupancy over time."""
    start, end = from_ts, to_ts
    if start is None or end is None:
        start, end = _default_time_range()
    floor_key = floor if floor is not None else "all"
    cache_key = f"cache:zones:{start.isoformat()}:{end.isoformat()}:{floor_key}:{interval}"
    redis = await get_redis()
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    stmt = (
        select(HeatmapSnapshot.timestamp, HeatmapSnapshot.zone_occupancy)
        .where(HeatmapSnapshot.timestamp >= start, HeatmapSnapshot.timestamp <= end)
        .order_by(HeatmapSnapshot.timestamp)
    )
    rows = (await db.execute(stmt)).all()
    series: dict[str, list[dict]] = {}
    bucket_seconds = interval * 60
    last_bucket: dict[str, int] = {}

    for ts, occupancy in rows:
        if not isinstance(occupancy, dict):
            continue
        bucket = int(ts.timestamp()) // bucket_seconds
        for zone_name, zdata in occupancy.items():
            if not isinstance(zdata, dict):
                continue
            if floor is not None and zdata.get("floor") != floor:
                continue
            key = f"{zone_name}:{bucket}"
            if key in last_bucket:
                continue
            last_bucket[key] = 1
            count = int(zdata.get("count", 0))
            pct = int(zdata.get("pct", 0))
            series.setdefault(zone_name, []).append(
                {
                    "timestamp": ts.astimezone(timezone.utc).strftime("%H:%M"),
                    "count": count,
                    "pct": pct,
                }
            )

    response = {"data": {"zones": series, "floor": floor}}
    await redis.setex(cache_key, ZONES_CACHE_TTL, json.dumps(response, default=str))
    return response
