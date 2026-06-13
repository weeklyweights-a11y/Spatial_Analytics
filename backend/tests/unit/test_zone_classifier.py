"""Unit tests for zone_classifier."""

import numpy as np
import supervision as sv

from backend.core.zone_classifier import ZoneClassifier
from backend.utils.zone_loader import ZoneConfig


def _make_zone_classifier() -> ZoneClassifier:
    zones = [
        ZoneConfig(
            name="Left",
            type="coding",
            camera_id="CAM-01",
            floor=0,
            capacity=10,
            polygon=[[0, 0], [400, 0], [400, 400], [0, 400]],
        ),
        ZoneConfig(
            name="Right",
            type="mentoring",
            camera_id="CAM-01",
            floor=0,
            capacity=10,
            polygon=[[500, 0], [900, 0], [900, 400], [500, 400]],
        ),
    ]
    return ZoneClassifier(zones)


def test_centroid_in_polygon_assignment():
    zc = _make_zone_classifier()
    detections = sv.Detections(
        xyxy=np.array([[50, 50, 150, 150], [550, 50, 650, 150]], dtype=np.float32),
        confidence=np.array([0.9, 0.9], dtype=np.float32),
        tracker_id=np.array([1, 2], dtype=int),
    )
    assignments = zc.assign_zones(detections)
    assert assignments[0].zone_name == "Left"
    assert assignments[0].zone_type == "coding"
    assert assignments[1].zone_name == "Right"
    assert assignments[1].zone_type == "mentoring"


def test_unassigned_outside_zones():
    zc = _make_zone_classifier()
    detections = sv.Detections(
        xyxy=np.array([[450, 50, 480, 150]], dtype=np.float32),
        confidence=np.array([0.9], dtype=np.float32),
        tracker_id=np.array([3], dtype=int),
    )
    assignments = zc.assign_zones(detections)
    assert assignments[0].zone_name == "unassigned"
