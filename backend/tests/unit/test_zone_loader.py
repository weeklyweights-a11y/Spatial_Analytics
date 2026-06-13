"""Unit tests for zone_loader."""

from pathlib import Path

from backend.utils.zone_loader import load_zones_yaml, zones_for_camera


def test_load_zones_yaml():
    root = Path(__file__).resolve().parents[3]
    zones = load_zones_yaml(root / "configs" / "zones.yaml")
    assert len(zones) >= 3
    assert zones[0].type in ("coding", "mentoring", "rest")


def test_zones_for_camera():
    root = Path(__file__).resolve().parents[3]
    zones = load_zones_yaml(root / "configs" / "zones.yaml")
    cam_zones = zones_for_camera(zones, "CAM-01")
    assert all(z.camera_id == "CAM-01" for z in cam_zones)
    assert len(cam_zones) >= 3
