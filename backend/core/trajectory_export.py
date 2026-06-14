"""OpenTraj trajectory export formatting and anonymization."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Iterator, Optional


def anonymize_id(participant_id: str) -> str:
    """SHA256 hash of participant UUID for external sharing."""
    return hashlib.sha256(participant_id.encode("utf-8")).hexdigest()[:16]


def bbox_centroid(bbox: Any) -> tuple[float, float]:
    """Compute centroid from bbox JSONB [x1,y1,x2,y2]."""
    if bbox is None:
        return 0.0, 0.0
    if isinstance(bbox, str):
        bbox = json.loads(bbox)
    if isinstance(bbox, dict):
        pts = bbox.get("points") or bbox.get("xyxy")
        if pts and len(pts) >= 4:
            x1, y1, x2, y2 = pts[:4]
            return (float(x1) + float(x2)) / 2.0, (float(y1) + float(y2)) / 2.0
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        x1, y1, x2, y2 = bbox[:4]
        return (float(x1) + float(x2)) / 2.0, (float(y1) + float(y2)) / 2.0
    return 0.0, 0.0


def format_opentraj_row(
    frame_id: int,
    pedestrian_id: str,
    pos_x: float,
    pos_y: float,
    activity: str,
    zone: str,
) -> str:
    """Format one OpenTraj TSV row."""
    return f"{frame_id}\t{pedestrian_id}\t{pos_x:.1f}\t{pos_y:.1f}\t{activity}\t{zone}\n"


def format_opentraj_header() -> str:
    return "frame_id\tpedestrian_id\tpos_x\tpos_y\tactivity\tzone\n"


def trajectory_rows_from_logs(
    rows: list[dict[str, Any]],
    anonymize: bool = False,
    start_frame_id: int = 1,
) -> Iterator[str]:
    """Yield OpenTraj TSV lines from activity log dict rows."""
    frame_id = start_frame_id
    for row in rows:
        pid = str(row["participant_id"])
        ped_id = anonymize_id(pid) if anonymize else pid
        cx, cy = bbox_centroid(row.get("bbox"))
        yield format_opentraj_row(
            frame_id,
            ped_id,
            cx,
            cy,
            str(row.get("activity", "idle")),
            str(row.get("zone_name", "unknown")),
        )
        frame_id += 1
