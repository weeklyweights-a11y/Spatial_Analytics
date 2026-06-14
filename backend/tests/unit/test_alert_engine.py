"""Unit tests for alert engine rules."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.core.alert_engine import evaluate_alerts


def _snapshot(zones: dict, energy: float = 0.5) -> dict:
    return {
        "zones": zones,
        "energy_level": energy,
        "total_active": 100,
        "total_registered": 1000,
    }


def _meta(name: str, ztype: str = "coding", floor: int = 0) -> dict:
    return {"name": name, "zone_type": ztype, "floor": floor, "capacity": 50}


@patch("backend.core.alert_engine.redis_sync.get_alert_cooldown", return_value=None)
@patch("backend.core.alert_engine.redis_sync.set_alert_cooldown")
def test_zone_capacity_fires_at_91(_set_cd, _get_cd) -> None:
    snap = _snapshot({"Coding Zone A": {"count": 46, "capacity": 50, "pct": 92, "floor": 0}})
    alerts = evaluate_alerts(snap, [_meta("Coding Zone A")])
    assert any(a["rule_name"] == "zone_capacity" for a in alerts)


@patch("backend.core.alert_engine.redis_sync.get_alert_cooldown", return_value=None)
@patch("backend.core.alert_engine.redis_sync.set_alert_cooldown")
def test_zone_capacity_silent_at_89(_set_cd, _get_cd) -> None:
    snap = _snapshot({"Coding Zone A": {"count": 44, "capacity": 50, "pct": 88, "floor": 0}})
    alerts = evaluate_alerts(snap, [_meta("Coding Zone A")])
    assert not any(a["rule_name"] == "zone_capacity" for a in alerts)


@patch("backend.core.alert_engine.redis_sync.get_alert_cooldown", return_value=120.0)
@patch("backend.core.alert_engine.redis_sync.set_alert_cooldown")
def test_cooldown_blocks_repeat(_set_cd, _get_cd) -> None:
    snap = _snapshot({"Coding Zone A": {"count": 46, "capacity": 50, "pct": 92, "floor": 0}})
    alerts = evaluate_alerts(snap, [_meta("Coding Zone A")])
    assert alerts == []


@patch("backend.core.alert_engine.redis_sync.get_alert_cooldown", return_value=None)
@patch("backend.core.alert_engine.redis_sync.set_alert_cooldown")
def test_energy_dip_at_20(_set_cd, _get_cd) -> None:
    snap = _snapshot({}, energy=0.20)
    alerts = evaluate_alerts(snap, [])
    assert any(a["rule_name"] == "energy_dip" for a in alerts)


@patch("backend.core.alert_engine.redis_sync.get_alert_cooldown", return_value=None)
@patch("backend.core.alert_engine.redis_sync.set_alert_cooldown")
def test_energy_ok_at_30(_set_cd, _get_cd) -> None:
    snap = _snapshot({}, energy=0.30)
    alerts = evaluate_alerts(snap, [])
    assert not any(a["rule_name"] == "energy_dip" for a in alerts)


@patch("backend.core.alert_engine.redis_sync.clear_zone_duration")
@patch("backend.core.alert_engine.redis_sync.get_zone_duration_since", return_value=None)
@patch("backend.core.alert_engine.redis_sync.get_alert_cooldown", return_value=None)
@patch("backend.core.alert_engine.redis_sync.set_alert_cooldown")
def test_mentor_empty_29_min_no_alert(_set_cd, _get_cd, _since, _clear) -> None:
    import time

    with patch("backend.core.alert_engine.time.time", return_value=1000.0):
        with patch("backend.core.alert_engine.redis_sync.get_zone_duration_since", return_value=1000.0 - 29 * 60):
            snap = _snapshot({"Mentor Booth": {"count": 0, "capacity": 10, "pct": 0, "floor": 1}})
            alerts = evaluate_alerts(snap, [_meta("Mentor Booth", "mentoring", 1)])
    assert not any(a["rule_name"] == "mentor_empty" for a in alerts)


@patch("backend.core.alert_engine.redis_sync.clear_zone_duration")
@patch("backend.core.alert_engine.redis_sync.get_alert_cooldown", return_value=None)
@patch("backend.core.alert_engine.redis_sync.set_alert_cooldown")
def test_mentor_empty_31_min_fires(_set_cd, _get_cd, _clear) -> None:
    with patch("backend.core.alert_engine.time.time", return_value=5000.0):
        with patch("backend.core.alert_engine.redis_sync.get_zone_duration_since", return_value=5000.0 - 31 * 60):
            snap = _snapshot({"Mentor Booth": {"count": 0, "capacity": 10, "pct": 0, "floor": 1}})
            alerts = evaluate_alerts(snap, [_meta("Mentor Booth", "mentoring", 1)])
    assert any(a["rule_name"] == "mentor_empty" for a in alerts)
