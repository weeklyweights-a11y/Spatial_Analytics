"""Supervision ByteTrack bridge for DEIMv2 detections."""

from __future__ import annotations

import numpy as np
import supervision as sv

from backend.config import get_settings


class PersonTracker:
    """ByteTrack + DetectionsSmoother over manual sv.Detections."""

    def __init__(self) -> None:
        settings = get_settings()
        cfg = settings.load_bytetrack_config()
        self.tracker = sv.ByteTrack(
            track_activation_threshold=float(cfg.get("track_activation_threshold", 0.25)),
            lost_track_buffer=int(cfg.get("lost_track_buffer", 30)),
            minimum_matching_threshold=float(cfg.get("minimum_matching_threshold", 0.8)),
            frame_rate=int(cfg.get("frame_rate", 10)),
        )
        self.smoother = sv.DetectionsSmoother(length=int(cfg.get("smoother_length", 5)))

    @staticmethod
    def from_deimv2(
        boxes: np.ndarray, scores: np.ndarray, keypoints: np.ndarray
    ) -> sv.Detections:
        """Build sv.Detections from DEIMv2 arrays (no Ultralytics)."""
        if len(boxes) == 0:
            return sv.Detections.empty()
        return sv.Detections(
            xyxy=boxes.astype(np.float32),
            confidence=scores.astype(np.float32),
            data={"keypoints": keypoints.astype(np.float32)},
        )

    def update(
        self, boxes: np.ndarray, scores: np.ndarray, keypoints: np.ndarray
    ) -> sv.Detections:
        """Track and smooth one frame of detections."""
        detections = self.from_deimv2(boxes, scores, keypoints)
        detections = self.tracker.update_with_detections(detections)
        return self.smoother.update_with_detections(detections)

    def reset(self) -> None:
        """Reset tracker state (e.g. on stream reconnect)."""
        settings = get_settings()
        cfg = settings.load_bytetrack_config()
        self.tracker = sv.ByteTrack(
            track_activation_threshold=float(cfg.get("track_activation_threshold", 0.25)),
            lost_track_buffer=int(cfg.get("lost_track_buffer", 30)),
            minimum_matching_threshold=float(cfg.get("minimum_matching_threshold", 0.8)),
            frame_rate=int(cfg.get("frame_rate", 10)),
        )
        self.smoother = sv.DetectionsSmoother(length=int(cfg.get("smoother_length", 5)))
