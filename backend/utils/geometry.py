"""Geometry helpers for face-to-body matching and zone assignment."""

from __future__ import annotations

import numpy as np


def bbox_centroid(bbox: np.ndarray) -> tuple[float, float]:
    """Centroid of xyxy bbox."""
    x1, y1, x2, y2 = bbox[:4]
    return (float(x1 + x2) / 2.0, float(y1 + y2) / 2.0)


def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def bbox_contains_point(bbox: np.ndarray, x: float, y: float) -> bool:
    """True if point lies inside bbox."""
    x1, y1, x2, y2 = bbox[:4]
    return x1 <= x <= x2 and y1 <= y <= y2


def bbox_iou(a: np.ndarray, b: np.ndarray) -> float:
    """IoU between two xyxy boxes."""
    x1 = max(float(a[0]), float(b[0]))
    y1 = max(float(a[1]), float(b[1]))
    x2 = min(float(a[2]), float(b[2]))
    y2 = min(float(a[3]), float(b[3]))
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = max(0.0, float(a[2] - a[0])) * max(0.0, float(a[3] - a[1]))
    area_b = max(0.0, float(b[2] - b[0])) * max(0.0, float(b[3] - b[1]))
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def face_center(face_bbox: np.ndarray) -> tuple[float, float]:
    """Center of face bbox."""
    return bbox_centroid(face_bbox)
