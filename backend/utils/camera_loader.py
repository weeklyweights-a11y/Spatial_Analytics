"""Load camera definitions from configs/cameras.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


class CameraConfig(BaseModel):
    """Camera entry from YAML."""

    id: str
    name: str
    rtsp_url: str
    floor: int = 0


def load_cameras_yaml(path: Optional[Path] = None) -> list[CameraConfig]:
    """Parse cameras.yaml."""
    if path is None:
        path = Path(__file__).resolve().parents[2] / "configs" / "cameras.yaml"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw = data.get("cameras") or []
    return [
        CameraConfig(
            id=item["id"],
            name=item.get("name", item["id"]),
            rtsp_url=item["rtsp_url"],
            floor=int(item.get("floor", 0)),
        )
        for item in raw
        if item
    ]
