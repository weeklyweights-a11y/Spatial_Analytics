"""Zone assignment via supervision PolygonZone."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import supervision as sv

from backend.utils.geometry import bbox_centroid, point_in_polygon
from backend.utils.zone_loader import ZoneConfig


@dataclass
class PersonZone:
    zone_name: str
    zone_type: str


class ZoneClassifier:
    """PolygonZone per configured zone; occupancy counts all tracks."""

    def __init__(self, zones: list[ZoneConfig]) -> None:
        self.zones = zones
        self._polygon_zones: list[tuple[ZoneConfig, sv.PolygonZone]] = []
        for z in zones:
            pts = np.array(z.polygon, dtype=np.int32)
            if len(pts) < 3:
                continue
            pz = sv.PolygonZone(polygon=pts)
            self._polygon_zones.append((z, pz))

    def trigger_occupancy(self, detections: sv.Detections) -> dict[str, int]:
        """Update PolygonZone triggers; return zone_name -> count (all tracks)."""
        counts: dict[str, int] = {}
        for zcfg, pzone in self._polygon_zones:
            pzone.trigger(detections)
            counts[zcfg.name] = int(pzone.current_count)
        return counts

    def assign_zones(self, detections: sv.Detections) -> list[PersonZone]:
        """Assign each detection to zone containing bbox centroid."""
        n = len(detections)
        if n == 0:
            return []
        results: list[PersonZone] = []
        for i in range(n):
            cx, cy = bbox_centroid(detections.xyxy[i])
            assigned = PersonZone(zone_name="unassigned", zone_type="unknown")
            for zcfg, _ in self._polygon_zones:
                if point_in_polygon(cx, cy, zcfg.polygon):
                    assigned = PersonZone(zone_name=zcfg.name, zone_type=zcfg.type)
                    break
            results.append(assigned)
        return results

    def zone_polygons(self) -> list[tuple[ZoneConfig, np.ndarray]]:
        return [(z, np.array(z.polygon, dtype=np.int32)) for z, _ in self._polygon_zones]
