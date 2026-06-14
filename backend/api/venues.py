"""Venue floor plan endpoints."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends

from backend.api.deps import CurrentUser, require_role
from backend.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["venues"])

FLOOR_NAMES = {
    0: "Ground Floor",
    1: "1st Floor",
    2: "2nd Floor",
}


def _floor_from_filename(name: str) -> tuple[int, str]:
    if "ground" in name.lower() or name.startswith("floor_0"):
        return 0, FLOOR_NAMES[0]
    m = re.search(r"floor_(\d+)", name)
    if m:
        n = int(m.group(1))
        return n, FLOOR_NAMES.get(n, f"Floor {n}")
    return 0, "Ground Floor"


@router.get("/venues/floors")
async def list_floors(
    user: CurrentUser = Depends(require_role(["admin", "operator", "viewer"])),
) -> dict:
    """List floor plans from data/venue/."""
    settings = get_settings()
    venue_dir = Path("/app/data/venue")
    if not venue_dir.exists():
        venue_dir = Path(__file__).resolve().parents[2] / "data" / "venue"
    floors = []
    if venue_dir.exists():
        for path in sorted(venue_dir.glob("floor_*.*")):
            if path.suffix.lower() not in {".png", ".svg", ".jpg", ".jpeg"}:
                continue
            floor_num, display = _floor_from_filename(path.stem)
            floors.append(
                {
                    "floor": floor_num,
                    "name": display,
                    "image_url": f"/static/venue/{path.name}",
                }
            )
    floors.sort(key=lambda f: f["floor"])
    if not floors:
        for n, label in FLOOR_NAMES.items():
            floors.append(
                {
                    "floor": n,
                    "name": label,
                    "image_url": f"/static/venue/floor_{n}_ground.png" if n == 0 else f"/static/venue/floor_{n}.png",
                }
            )
    return {"data": {"floors": floors}}
