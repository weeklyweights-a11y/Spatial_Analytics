"""Build heatmap occupancy snapshots from Redis + DB zone metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_heatmap_snapshot(
    occupancy: dict[str, int],
    zone_metadata: list[dict[str, Any]],
    total_active: int,
    total_registered: int,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Build snapshot dict for Redis, WebSocket, and PostgreSQL."""
    ts = timestamp or datetime.now(timezone.utc)
    meta_by_name = {z["name"]: z for z in zone_metadata}
    zones_out: dict[str, dict[str, Any]] = {}

    all_names = set(occupancy.keys()) | set(meta_by_name.keys())
    for name in sorted(all_names):
        meta = meta_by_name.get(name, {})
        count = int(occupancy.get(name, 0))
        capacity = int(meta.get("capacity") or 50)
        pct = int(min(100, round((count / capacity) * 100))) if capacity > 0 else 0
        zones_out[name] = {
            "count": count,
            "capacity": capacity,
            "pct": pct,
            "floor": int(meta.get("floor", 0)),
        }

    energy = 0.0
    if total_registered > 0:
        energy = min(1.0, total_active / total_registered)

    return {
        "zones": zones_out,
        "total_active": total_active,
        "total_registered": total_registered,
        "energy_level": round(energy, 4),
        "timestamp": ts.isoformat(),
    }
