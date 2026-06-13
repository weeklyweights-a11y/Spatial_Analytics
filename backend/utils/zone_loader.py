"""Load zone definitions from configs/zones.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class ZoneConfig(BaseModel):
    """Single zone from YAML (spec uses `type` and `polygon`)."""

    name: str
    type: str = Field(description="Zone type: coding, mentoring, presenting, etc.")
    camera_id: str
    floor: int = 0
    capacity: int = 50
    polygon: list[list[float]]
    sponsor_name: Optional[str] = None

    @property
    def zone_type(self) -> str:
        """Alias for DB `zone_type` column."""
        return self.type


def load_zones_yaml(path: Optional[Path] = None) -> list[ZoneConfig]:
    """Parse zones.yaml; returns empty list if missing."""
    if path is None:
        path = Path(__file__).resolve().parents[2] / "configs" / "zones.yaml"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw = data.get("zones") or []
    zones: list[ZoneConfig] = []
    for item in raw:
        if not item:
            continue
        poly = item.get("polygon") or item.get("polygon_coords") or []
        zones.append(
            ZoneConfig(
                name=item["name"],
                type=item.get("type") or item.get("zone_type", "coding"),
                camera_id=item["camera_id"],
                floor=int(item.get("floor", 0)),
                capacity=int(item.get("capacity", 50)),
                polygon=poly,
                sponsor_name=item.get("sponsor_name"),
            )
        )
    return zones


def zones_for_camera(zones: list[ZoneConfig], camera_id: str) -> list[ZoneConfig]:
    """Filter zones assigned to a camera."""
    return [z for z in zones if z.camera_id == camera_id]
