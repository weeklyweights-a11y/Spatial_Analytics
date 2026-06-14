"""Rule-based alert engine for heatmap worker snapshots."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.db import redis_sync


@dataclass
class AlertRule:
    """Single alert rule with cooldown."""

    name: str
    severity: str
    cooldown_seconds: int
    check: Callable[[dict[str, Any], dict[str, Any]], Optional[dict[str, Any]]]


def _zone_capacity_alert(snapshot: dict[str, Any], _ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    for name, z in snapshot.get("zones", {}).items():
        capacity = z.get("capacity", 0)
        count = z.get("count", 0)
        if capacity <= 0:
            continue
        pct = count / capacity
        if pct > 0.9:
            return {
                "rule_name": "zone_capacity",
                "severity": "warning",
                "message": f"{name} at {int(pct * 100)}% capacity ({count}/{capacity})",
                "zone": name,
                "floor": z.get("floor"),
                "cooldown_key": name,
            }
    return None


def _mentor_empty_alert(snapshot: dict[str, Any], ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    zone_types = ctx.get("zone_types", {})
    now = time.time()
    for name, z in snapshot.get("zones", {}).items():
        if zone_types.get(name) != "mentoring":
            continue
        count = z.get("count", 0)
        if count > 0:
            redis_sync.clear_zone_duration("empty", name)
            continue
        since = redis_sync.get_zone_duration_since("empty", name)
        if since is None:
            redis_sync.set_zone_duration_since("empty", name, now)
            continue
        minutes = int((now - since) / 60)
        if minutes >= 30:
            return {
                "rule_name": "mentor_empty",
                "severity": "warning",
                "message": f"Mentor booth on floor {z.get('floor', 0)} empty for {minutes} minutes",
                "zone": name,
                "floor": z.get("floor"),
                "cooldown_key": name,
            }
    return None


def _energy_dip_alert(snapshot: dict[str, Any], _ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    energy = float(snapshot.get("energy_level", 1.0))
    if energy < 0.25:
        pct = int(energy * 100)
        return {
            "rule_name": "energy_dip",
            "severity": "info",
            "message": f"Event energy at {pct}% — consider food, music, or an announcement",
            "zone": None,
            "floor": None,
            "cooldown_key": "global",
        }
    return None


def _zone_empty_alert(snapshot: dict[str, Any], ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    zone_types = ctx.get("zone_types", {})
    for name, z in snapshot.get("zones", {}).items():
        ztype = zone_types.get(name, "")
        if ztype not in ("coding", "networking"):
            continue
        if z.get("count", 0) == 0:
            return {
                "rule_name": "zone_empty",
                "severity": "info",
                "message": f"{name} is completely empty",
                "zone": name,
                "floor": z.get("floor"),
                "cooldown_key": name,
            }
    return None


def _sustained_high_load_alert(snapshot: dict[str, Any], _ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    now = time.time()
    for name, z in snapshot.get("zones", {}).items():
        capacity = z.get("capacity", 0)
        count = z.get("count", 0)
        if capacity <= 0:
            continue
        pct = count / capacity
        if pct > 0.85:
            since = redis_sync.get_zone_duration_since("high", name)
            if since is None:
                redis_sync.set_zone_duration_since("high", name, now)
                continue
            minutes = int((now - since) / 60)
            if minutes >= 30:
                return {
                    "rule_name": "sustained_high_load",
                    "severity": "warning",
                    "message": (
                        f"{name} has been above 85% capacity for {minutes} minutes "
                        "— consider directing people elsewhere"
                    ),
                    "zone": name,
                    "floor": z.get("floor"),
                    "cooldown_key": name,
                }
        else:
            redis_sync.clear_zone_duration("high", name)
    return None


DEFAULT_RULES: list[AlertRule] = [
    AlertRule("zone_capacity", "warning", 600, _zone_capacity_alert),
    AlertRule("mentor_empty", "warning", 1800, _mentor_empty_alert),
    AlertRule("energy_dip", "info", 1800, _energy_dip_alert),
    AlertRule("zone_empty", "info", 3600, _zone_empty_alert),
    AlertRule("sustained_high_load", "warning", 1800, _sustained_high_load_alert),
]


def evaluate_alerts(
    snapshot: dict[str, Any],
    zone_metadata: list[dict[str, Any]],
    rules: list[AlertRule] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate rules; return list of alert dicts ready to persist/publish."""
    ctx = {
        "zone_types": {z["name"]: z.get("zone_type", "") for z in zone_metadata},
    }
    fired: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for rule in rules or DEFAULT_RULES:
        result = rule.check(snapshot, ctx)
        if result is None:
            continue
        cooldown_key = result.get("cooldown_key", "global")
        if redis_sync.get_alert_cooldown(rule.name, str(cooldown_key)) is not None:
            continue
        redis_sync.set_alert_cooldown(rule.name, str(cooldown_key), rule.cooldown_seconds)
        alert_id = str(uuid.uuid4())
        fired.append(
            {
                "type": "alert",
                "id": alert_id,
                "rule_name": result["rule_name"],
                "severity": result["severity"],
                "message": result["message"],
                "zone": result.get("zone"),
                "floor": result.get("floor"),
                "timestamp": now.isoformat(),
            }
        )
    return fired
