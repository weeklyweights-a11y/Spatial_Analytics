#!/usr/bin/env python3
"""Sync zones and cameras from YAML configs into PostgreSQL (idempotent)."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import yaml
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import get_settings
from backend.db.models import Camera, Zone

ZONE_IDS_PATH = ROOT / "data" / "venue" / "zone_ids.json"


def _load_zone_id_map() -> dict[str, str]:
    """Load or initialize stable zone name -> UUID mapping."""
    if ZONE_IDS_PATH.exists():
        return json.loads(ZONE_IDS_PATH.read_text(encoding="utf-8"))
    return {}


def _save_zone_id_map(mapping: dict[str, str]) -> None:
    ZONE_IDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ZONE_IDS_PATH.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")


def _zone_uuid(name: str, mapping: dict[str, str]) -> uuid.UUID:
    if name not in mapping:
        mapping[name] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"spatialscore.zone.{name}"))
    return uuid.UUID(mapping[name])


def sync_venue(session: Session, configs_dir: Path) -> tuple[int, int]:
    """Upsert zones and cameras; return (zones_count, cameras_count)."""
    zones_path = configs_dir / "zones.yaml"
    cameras_path = configs_dir / "cameras.yaml"

    zones_data = yaml.safe_load(zones_path.read_text(encoding="utf-8")) or {}
    cameras_data = yaml.safe_load(cameras_path.read_text(encoding="utf-8")) or {}

    zone_id_map = _load_zone_id_map()
    zones_synced = 0

    for z in zones_data.get("zones", []):
        name = z["name"]
        zone_id = _zone_uuid(name, zone_id_map)
        polygon = z.get("polygon", [])
        floor_poly = z.get("floor_polygon")
        existing = session.get(Zone, zone_id)
        fields = {
            "name": name,
            "zone_type": z.get("type", "coding"),
            "camera_id": z.get("camera_id", ""),
            "polygon_coords": {"points": polygon},
            "floor_polygon": {"points": floor_poly} if floor_poly else None,
            "floor": int(z.get("floor", 0)),
            "capacity": z.get("capacity"),
        }
        if existing is None:
            session.add(Zone(id=zone_id, **fields))
        else:
            for key, val in fields.items():
                setattr(existing, key, val)
        zones_synced += 1

    _save_zone_id_map(zone_id_map)

    cameras_synced = 0
    for c in cameras_data.get("cameras", []):
        cam_id = c["id"]
        existing = session.get(Camera, cam_id)
        fields = {
            "name": c.get("name", cam_id),
            "rtsp_url": c.get("rtsp_url", ""),
            "camera_type": c.get("type", "cctv"),
            "floor": c.get("floor"),
            "is_active": c.get("is_active", True),
        }
        if existing is None:
            session.add(Camera(id=cam_id, **fields))
        else:
            for key, val in fields.items():
                setattr(existing, key, val)
        cameras_synced += 1

    session.commit()
    return zones_synced, cameras_synced


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.worker_database_url)
    configs_dir = Path(settings.CONFIGS_DIR)
    if not configs_dir.exists():
        configs_dir = ROOT / "configs"

    with Session(engine) as session:
        zones_n, cams_n = sync_venue(session, configs_dir)
    logger.info(f"Synced {zones_n} zones and {cams_n} cameras from {configs_dir}")


if __name__ == "__main__":
    main()
