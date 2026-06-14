"""Load sponsor entrance lines from zones.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from backend.config import get_settings


@dataclass(frozen=True)
class SponsorLineConfig:
    """Single sponsor LineZone definition."""

    name: str
    camera_id: str
    sponsor_name: str
    start: tuple[int, int]
    end: tuple[int, int]
    sponsor_id: Optional[str] = None


def _configs_dir() -> Path:
    settings = get_settings()
    path = Path(settings.CONFIGS_DIR)
    if path.exists():
        return path
    return Path(__file__).resolve().parents[2] / "configs"


def load_sponsor_lines_yaml(configs_dir: Optional[Path] = None) -> list[SponsorLineConfig]:
    """Parse sponsor_lines block from zones.yaml."""
    base = configs_dir or _configs_dir()
    zones_path = base / "zones.yaml"
    if not zones_path.exists():
        return []
    data = yaml.safe_load(zones_path.read_text(encoding="utf-8")) or {}
    lines: list[SponsorLineConfig] = []
    for raw in data.get("sponsor_lines", []):
        start = raw.get("start", [0, 0])
        end = raw.get("end", [0, 0])
        lines.append(
            SponsorLineConfig(
                name=str(raw.get("name", "")),
                camera_id=str(raw.get("camera_id", "")),
                sponsor_name=str(raw.get("sponsor_name", "")),
                start=(int(start[0]), int(start[1])),
                end=(int(end[0]), int(end[1])),
            )
        )
    return lines


def sponsor_lines_for_camera(
    camera_id: str,
    configs_dir: Optional[Path] = None,
) -> list[SponsorLineConfig]:
    """Filter sponsor lines for a single camera."""
    return [line for line in load_sponsor_lines_yaml(configs_dir) if line.camera_id == camera_id]


def attach_sponsor_ids(
    lines: list[SponsorLineConfig],
    name_to_id: dict[str, str],
) -> list[SponsorLineConfig]:
    """Return lines with sponsor_id resolved from DB name map."""
    result: list[SponsorLineConfig] = []
    for line in lines:
        sid = name_to_id.get(line.sponsor_name)
        result.append(
            SponsorLineConfig(
                name=line.name,
                camera_id=line.camera_id,
                sponsor_name=line.sponsor_name,
                start=line.start,
                end=line.end,
                sponsor_id=sid,
            )
        )
    return result
