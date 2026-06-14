"""Unit tests for heatmap snapshot builder."""

from __future__ import annotations

from backend.core.heatmap_snapshot import build_heatmap_snapshot


def test_snapshot_counts_and_energy() -> None:
    snap = build_heatmap_snapshot(
        occupancy={"Coding Zone A": 25},
        zone_metadata=[{"name": "Coding Zone A", "capacity": 50, "floor": 0, "zone_type": "coding"}],
        total_active=500,
        total_registered=1000,
    )
    assert snap["zones"]["Coding Zone A"]["count"] == 25
    assert snap["zones"]["Coding Zone A"]["pct"] == 50
    assert snap["energy_level"] == 0.5
