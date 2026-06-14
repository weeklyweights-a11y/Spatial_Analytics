"""Unit tests for trajectory export formatting."""

from __future__ import annotations

import uuid

from backend.core.trajectory_export import (
    anonymize_id,
    bbox_centroid,
    format_opentraj_header,
    trajectory_rows_from_logs,
)


def test_opentraj_schema() -> None:
    pid = str(uuid.uuid4())
    rows = [
        {
            "participant_id": pid,
            "activity": "coding",
            "bbox": [100.0, 200.0, 150.0, 280.0],
            "zone_name": "Coding Zone A",
        }
    ]
    header = format_opentraj_header()
    assert "frame_id" in header
    lines = list(trajectory_rows_from_logs(rows, anonymize=False, start_frame_id=1))
    assert len(lines) == 1
    parts = lines[0].strip().split("\t")
    assert parts[0] == "1"
    assert parts[1] == pid
    assert parts[2] == "125.0"
    assert parts[3] == "240.0"
    assert parts[4] == "coding"
    assert parts[5] == "Coding Zone A"


def test_anonymize_hides_uuid() -> None:
    pid = str(uuid.uuid4())
    rows = [{"participant_id": pid, "activity": "idle", "bbox": None, "zone_name": "Rest"}]
    lines = list(trajectory_rows_from_logs(rows, anonymize=True))
    assert pid not in lines[0]
    assert anonymize_id(pid) in lines[0]


def test_bbox_centroid_dict() -> None:
    cx, cy = bbox_centroid({"xyxy": [0, 0, 100, 200]})
    assert cx == 50.0
    assert cy == 100.0
