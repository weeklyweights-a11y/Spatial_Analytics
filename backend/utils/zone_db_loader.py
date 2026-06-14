"""Load zone definitions from PostgreSQL for camera workers."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Zone


def normalize_polygon(raw: Any) -> list[list[float]]:
    """Accept polygon as list or {\"points\": list}."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        points = raw.get("points") or raw.get("polygon") or []
        return [[float(p[0]), float(p[1])] for p in points]
    if isinstance(raw, list):
        return [[float(p[0]), float(p[1])] for p in raw]
    return []


def load_zones_from_db(session: Session, camera_id: str) -> list[dict[str, Any]]:
    """Load zones for a camera from Postgres."""
    rows = session.execute(
        select(Zone).where(Zone.camera_id == camera_id)
    ).scalars().all()
    zones: list[dict[str, Any]] = []
    for z in rows:
        zones.append(
            {
                "id": str(z.id),
                "name": z.name,
                "zone_type": z.zone_type,
                "camera_id": z.camera_id,
                "floor": z.floor,
                "capacity": z.capacity or 50,
                "polygon": normalize_polygon(z.polygon_coords),
                "floor_polygon": normalize_polygon(z.floor_polygon),
            }
        )
    return zones


def load_all_zones_from_db(session: Session) -> list[dict[str, Any]]:
    """Load all zones from Postgres."""
    rows = session.execute(select(Zone)).scalars().all()
    return [
        {
            "id": str(z.id),
            "name": z.name,
            "zone_type": z.zone_type,
            "camera_id": z.camera_id,
            "floor": z.floor,
            "capacity": z.capacity or 50,
            "polygon": normalize_polygon(z.polygon_coords),
            "floor_polygon": normalize_polygon(z.floor_polygon),
        }
        for z in rows
    ]
