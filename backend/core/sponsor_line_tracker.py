"""Sponsor booth entrance LineZone tracking via supervision."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import supervision as sv

from backend.utils.sponsor_line_loader import SponsorLineConfig


@dataclass
class SponsorLineTracker:
    """Wraps sv.LineZone for one sponsor entrance line."""

    config: SponsorLineConfig
    line_zone: sv.LineZone

    @classmethod
    def from_config(cls, config: SponsorLineConfig) -> "SponsorLineTracker":
        """Build LineZone from YAML config."""
        start = sv.Point(config.start[0], config.start[1])
        end = sv.Point(config.end[0], config.end[1])
        return cls(config=config, line_zone=sv.LineZone(start=start, end=end))

    def trigger(self, detections: sv.Detections) -> tuple[np.ndarray, np.ndarray]:
        """Return (crossed_in, crossed_out) boolean masks aligned with detections."""
        if detections.is_empty() or detections.tracker_id is None:
            empty = np.array([], dtype=bool)
            return empty, empty
        result = self.line_zone.trigger(detections)
        if isinstance(result, tuple) and len(result) == 2:
            return result[0], result[1]
        crossed_in = np.asarray(result, dtype=bool)
        return crossed_in, np.zeros_like(crossed_in)


class SponsorLineTrackerSet:
    """All sponsor lines for one camera."""

    def __init__(self, lines: list[SponsorLineConfig]) -> None:
        self._trackers: list[SponsorLineTracker] = [
            SponsorLineTracker.from_config(line) for line in lines if line.sponsor_id
        ]

    def reload(self, lines: list[SponsorLineConfig]) -> None:
        """Replace trackers after config reload."""
        self._trackers = [
            SponsorLineTracker.from_config(line) for line in lines if line.sponsor_id
        ]

    def trigger_all(
        self, detections: sv.Detections
    ) -> list[tuple[SponsorLineTracker, np.ndarray, np.ndarray]]:
        """Run all line zones; return tracker with in/out masks."""
        results: list[tuple[SponsorLineTracker, np.ndarray, np.ndarray]] = []
        for tracker in self._trackers:
            crossed_in, crossed_out = tracker.trigger(detections)
            results.append((tracker, crossed_in, crossed_out))
        return results

    @property
    def count(self) -> int:
        return len(self._trackers)
