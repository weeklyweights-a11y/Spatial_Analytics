"""Zone CRUD REST endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, require_role
from backend.db.database import get_db
from backend.db.models import ActivityLog, Zone
from backend.db.redis_client import publish_zones_updated
from backend.middleware.rate_limit import limiter
from backend.utils.zone_db_loader import normalize_polygon

router = APIRouter(prefix="/api/v1", tags=["zones"])


class ZoneCreateRequest(BaseModel):
    """Create zone payload."""

    name: str
    zone_type: str
    camera_id: str
    polygon_coords: list[list[float]]
    floor_polygon: Optional[list[list[float]]] = None
    floor: int = 0
    capacity: int = 50


class ZoneUpdateRequest(BaseModel):
    """Update zone payload."""

    name: Optional[str] = None
    zone_type: Optional[str] = None
    polygon_coords: Optional[list[list[float]]] = None
    floor_polygon: Optional[list[list[float]]] = None
    floor: Optional[int] = None
    capacity: Optional[int] = None


def _zone_to_dict(z: Zone) -> dict[str, Any]:
    return {
        "id": str(z.id),
        "name": z.name,
        "zone_type": z.zone_type,
        "camera_id": z.camera_id,
        "polygon_coords": normalize_polygon(z.polygon_coords),
        "floor_polygon": normalize_polygon(z.floor_polygon),
        "floor": z.floor,
        "capacity": z.capacity,
    }


@router.get("/zones")
async def list_zones(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin", "operator", "viewer"])),
    camera_id: Optional[str] = Query(None),
    floor: Optional[int] = Query(None),
) -> dict:
    """List zones, optionally filtered."""
    stmt = select(Zone)
    if camera_id:
        stmt = stmt.where(Zone.camera_id == camera_id)
    if floor is not None:
        stmt = stmt.where(Zone.floor == floor)
    rows = (await db.execute(stmt)).scalars().all()
    return {"data": [_zone_to_dict(z) for z in rows]}


@router.post("/zones")
@limiter.limit("10/minute")
async def create_zone(
    request: Request,
    body: ZoneCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin"])),
) -> dict:
    """Create a new zone."""
    zone = Zone(
        id=uuid.uuid4(),
        name=body.name,
        zone_type=body.zone_type,
        camera_id=body.camera_id,
        polygon_coords={"points": body.polygon_coords},
        floor_polygon={"points": body.floor_polygon} if body.floor_polygon else None,
        floor=body.floor,
        capacity=body.capacity,
    )
    db.add(zone)
    await db.commit()
    await db.refresh(zone)
    await publish_zones_updated()
    return {"data": _zone_to_dict(zone)}


@router.put("/zones/{zone_id}")
@limiter.limit("10/minute")
async def update_zone(
    request: Request,
    zone_id: UUID,
    body: ZoneUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin"])),
) -> dict:
    """Update zone properties."""
    zone = await db.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail={"error": "Zone not found", "code": "NOT_FOUND"})
    if body.name is not None:
        zone.name = body.name
    if body.zone_type is not None:
        zone.zone_type = body.zone_type
    if body.polygon_coords is not None:
        zone.polygon_coords = {"points": body.polygon_coords}
    if body.floor_polygon is not None:
        zone.floor_polygon = {"points": body.floor_polygon}
    if body.floor is not None:
        zone.floor = body.floor
    if body.capacity is not None:
        zone.capacity = body.capacity
    await db.commit()
    await db.refresh(zone)
    await publish_zones_updated()
    return {"data": _zone_to_dict(zone)}


@router.delete("/zones/{zone_id}")
@limiter.limit("10/minute")
async def delete_zone(
    request: Request,
    zone_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin"])),
) -> dict:
    """Delete zone if no activity logs reference it."""
    zone = await db.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail={"error": "Zone not found", "code": "NOT_FOUND"})
    log_count = await db.scalar(
        select(func.count()).select_from(ActivityLog).where(ActivityLog.zone_id == zone_id)
    )
    if log_count and log_count > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "Cannot delete zone with activity history",
                "code": "ZONE_IN_USE",
            },
        )
    await db.delete(zone)
    await db.commit()
    await publish_zones_updated()
    return {"data": {"id": str(zone_id), "deleted": True}}
