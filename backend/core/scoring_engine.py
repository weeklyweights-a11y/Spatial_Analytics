"""Pure scoring logic — no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from loguru import logger

ACTIVITY_TO_MINUTE_COLUMN: dict[str, str] = {
    "coding": "coding_minutes",
    "collaborating": "collaborating_minutes",
    "mentoring": "mentoring_minutes",
    "presenting": "presenting_minutes",
    "networking": "networking_minutes",
    "helping_others": "helping_minutes",
    "idle": "idle_minutes",
    "resting": "idle_minutes",
    "eating": "idle_minutes",
    "sponsor_engagement": "idle_minutes",
}

RADAR_AXES = ("coding", "collaborating", "mentoring", "presenting", "networking")


@dataclass
class ScoringWeight:
    """Weight and min dwell for one activity."""

    activity: str
    weight: float
    min_dwell_seconds: int


@dataclass
class ScoreRowSnapshot:
    """Minimal score row fields for tag assignment."""

    coding_minutes: float = 0.0
    collaborating_minutes: float = 0.0
    mentoring_minutes: float = 0.0
    presenting_minutes: float = 0.0
    networking_minutes: float = 0.0
    helping_minutes: float = 0.0
    idle_minutes: float = 0.0
    tags: list[str] = field(default_factory=list)


def load_scoring_config_from_yaml(path: Path) -> dict[str, ScoringWeight]:
    """Load scoring weights from YAML fallback."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    result: dict[str, ScoringWeight] = {}
    for activity, cfg in (data.get("activities") or {}).items():
        result[activity] = ScoringWeight(
            activity=activity,
            weight=float(cfg.get("weight", 0)),
            min_dwell_seconds=int(cfg.get("min_dwell_seconds", 0)),
        )
    return result


def load_scoring_config(rows: Optional[list[tuple[str, float, int]]] = None, yaml_path: Optional[Path] = None) -> dict[str, ScoringWeight]:
    """Build config dict from DB rows or YAML fallback."""
    if rows:
        return {
            activity: ScoringWeight(activity=activity, weight=weight, min_dwell_seconds=min_dwell)
            for activity, weight, min_dwell in rows
        }
    if yaml_path is None:
        yaml_path = Path(__file__).resolve().parents[2] / "configs" / "scoring.yaml"
    return load_scoring_config_from_yaml(yaml_path)


def aggregate_events_by_participant(
    events: list[dict[str, Any]],
    flush_interval_seconds: int = 60,
) -> dict[str, dict[str, float]]:
    """Group events by participant_id; count per activity; convert to fractional minutes."""
    by_participant: dict[str, dict[str, int]] = {}
    for ev in events:
        pid = str(ev.get("participant_id", ""))
        if not pid:
            continue
        activity = str(ev.get("activity", "idle"))
        by_participant.setdefault(pid, {})
        by_participant[pid][activity] = by_participant[pid].get(activity, 0) + 1

    minutes_map: dict[str, dict[str, float]] = {}
    for pid, counts in by_participant.items():
        total_events = sum(counts.values()) or 1
        cycle_minutes = flush_interval_seconds / 60.0
        activity_minutes: dict[str, float] = {}
        for activity, count in counts.items():
            activity_minutes[activity] = cycle_minutes * (count / total_events)
        minutes_map[pid] = activity_minutes
    return minutes_map


def apply_min_dwell(
    minutes_by_activity: dict[str, float],
    config: dict[str, ScoringWeight],
) -> dict[str, float]:
    """Zero out activities below min_dwell_seconds for this cycle."""
    result = dict(minutes_by_activity)
    for activity, minutes in list(result.items()):
        cfg = config.get(activity)
        if cfg is None:
            logger.warning(f"Unknown activity in scoring flush: {activity}")
            result.pop(activity, None)
            continue
        min_minutes = cfg.min_dwell_seconds / 60.0
        if minutes < min_minutes:
            result[activity] = 0.0
    return result


def calculate_period_points(
    minutes: dict[str, float],
    config: dict[str, ScoringWeight],
) -> float:
    """Sum minutes × weight for one participant cycle."""
    total = 0.0
    for activity, mins in minutes.items():
        cfg = config.get(activity)
        if cfg is None:
            continue
        total += mins * cfg.weight
    return total


def _total_activity_minutes(row: ScoreRowSnapshot) -> float:
    return (
        row.coding_minutes
        + row.collaborating_minutes
        + row.mentoring_minutes
        + row.presenting_minutes
        + row.networking_minutes
        + row.helping_minutes
        + row.idle_minutes
    )


def assign_tags(
    row: ScoreRowSnapshot,
    last_seen_at: Optional[datetime],
    visited_zone_count: int = 0,
) -> list[str]:
    """Assign behavioral tags from cumulative minutes and last_seen."""
    tags: list[str] = []
    total = _total_activity_minutes(row)
    if total <= 0:
        if last_seen_at and _is_night_owl(last_seen_at):
            tags.append("Night Owl")
        if visited_zone_count >= 3:
            tags.append("Cross-Pollinator")
        return tags

    if row.coding_minutes / total > 0.50:
        tags.append("Builder")
    if (row.mentoring_minutes + row.helping_minutes) / total > 0.15:
        tags.append("Mentor")
    if row.collaborating_minutes / total > 0.30:
        tags.append("Collaborator")
    if row.networking_minutes / total > 0.20:
        tags.append("Networker")
    if last_seen_at and _is_night_owl(last_seen_at):
        tags.append("Night Owl")
    if visited_zone_count >= 3:
        tags.append("Cross-Pollinator")
    return tags


def _is_night_owl(ts: datetime) -> bool:
    """Night Owl: active between 02:00 and 05:00 UTC."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    hour = ts.astimezone(timezone.utc).hour
    return 2 <= hour < 5


def build_radar_data(minutes_dict: dict[str, float]) -> list[dict[str, Any]]:
    """Five-axis radar as fractions of scored activity time (excludes idle/rest)."""
    axis_minutes = {axis: minutes_dict.get(axis, 0.0) for axis in RADAR_AXES}
    denom = sum(axis_minutes.values()) or 1.0
    return [{"axis": axis.replace("_", " ").title(), "value": axis_minutes[axis] / denom} for axis in RADAR_AXES]


def minute_column_for_activity(activity: str) -> Optional[str]:
    """Map event activity string to scores table column."""
    col = ACTIVITY_TO_MINUTE_COLUMN.get(activity)
    if col is None:
        logger.warning(f"No minute column mapping for activity: {activity}")
    return col


def merge_minutes_into_row(row: ScoreRowSnapshot, cycle_minutes: dict[str, float]) -> ScoreRowSnapshot:
    """Add cycle minutes into score row snapshot."""
    for activity, mins in cycle_minutes.items():
        col = minute_column_for_activity(activity)
        if col is None:
            continue
        current = getattr(row, col, 0.0)
        setattr(row, col, current + mins)
    return row
