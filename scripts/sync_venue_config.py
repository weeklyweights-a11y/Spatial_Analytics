#!/usr/bin/env python3
"""Sync zones, cameras, and sponsors from YAML configs into PostgreSQL (idempotent)."""

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
from backend.db.models import Camera, Sponsor, Zone

ZONE_IDS_PATH = ROOT / "data" / "venue" / "zone_ids.json"
SPONSOR_IDS_PATH = ROOT / "data" / "venue" / "sponsor_ids.json"


def _load_id_map(path: Path) -> dict[str, str]:
    """Load or initialize stable name -> UUID mapping."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_id_map(path: Path, mapping: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")


def _stable_uuid(namespace: str, name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"spatialscore.{namespace}.{name}")


def sync_venue(session: Session, configs_dir: Path) -> tuple[int, int, int]:
    """Upsert zones, cameras, and sponsors; return (zones, cameras, sponsors) counts."""
    zones_path = configs_dir / "zones.yaml"
    cameras_path = configs_dir / "cameras.yaml"
    sponsors_path = configs_dir / "sponsors.yaml"

    zones_data = yaml.safe_load(zones_path.read_text(encoding="utf-8")) or {}
    cameras_data = yaml.safe_load(cameras_path.read_text(encoding="utf-8")) or {}
    sponsors_data = yaml.safe_load(sponsors_path.read_text(encoding="utf-8")) if sponsors_path.exists() else {}

    zone_id_map = _load_id_map(ZONE_IDS_PATH)
    zones_synced = 0
    zone_name_to_id: dict[str, uuid.UUID] = {}

    for z in zones_data.get("zones", []):
        name = z["name"]
        zone_id = _stable_uuid("zone", name)
        if name not in zone_id_map:
            zone_id_map[name] = str(zone_id)
        else:
            zone_id = uuid.UUID(zone_id_map[name])
        zone_name_to_id[name] = zone_id
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

    _save_id_map(ZONE_IDS_PATH, zone_id_map)

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

    sponsor_id_map = _load_id_map(SPONSOR_IDS_PATH)
    sponsors_synced = 0
    for s in sponsors_data.get("sponsors", []):
        name = s["name"]
        sponsor_id = _stable_uuid("sponsor", name)
        if name not in sponsor_id_map:
            sponsor_id_map[name] = str(sponsor_id)
        else:
            sponsor_id = uuid.UUID(sponsor_id_map[name])
        booth_zone_name = s.get("booth_zone_name")
        booth_zone_id = zone_name_to_id.get(booth_zone_name) if booth_zone_name else None
        existing = session.get(Sponsor, sponsor_id)
        fields = {
            "name": name,
            "tier": s.get("tier"),
            "booth_zone_id": booth_zone_id,
            "logo_url": s.get("logo_url"),
            "contact_email": s.get("contact_email"),
        }
        if existing is None:
            session.add(Sponsor(id=sponsor_id, **fields))
        else:
            for key, val in fields.items():
                setattr(existing, key, val)
        if booth_zone_id is not None:
            zone_row = session.get(Zone, booth_zone_id)
            if zone_row is not None:
                zone_row.sponsor_id = sponsor_id
        sponsors_synced += 1

    _save_id_map(SPONSOR_IDS_PATH, sponsor_id_map)
    session.commit()
    return zones_synced, cameras_synced, sponsors_synced


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.worker_database_url)
    configs_dir = Path(settings.CONFIGS_DIR)
    if not configs_dir.exists():
        configs_dir = ROOT / "configs"

    with Session(engine) as session:
        zones_n, cams_n, sponsors_n = sync_venue(session, configs_dir)
    logger.info(
        f"Synced {zones_n} zones, {cams_n} cameras, and {sponsors_n} sponsors from {configs_dir}"
    )


if __name__ == "__main__":
    main()
