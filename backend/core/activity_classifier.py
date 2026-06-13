"""Activity classification from zone type + keypoint heuristics."""

from __future__ import annotations

from typing import Optional

import numpy as np

# Keypoint indices (DEIMv2 wholebody49 body subset 0-16)
_NOSE = 0
_L_SHOULDER, _R_SHOULDER = 5, 6
_L_ELBOW, _R_ELBOW = 7, 8
_L_WRIST, _R_WRIST = 9, 10
_L_HIP, _R_HIP = 11, 12


class ActivityClassifier:
    """Zone-based rules with hand motion heuristics for coding zones."""

    def __init__(self) -> None:
        self._prev_keypoints: dict[int, np.ndarray] = {}

    def classify(
        self,
        track_id: int,
        zone_type: str,
        keypoints: Optional[np.ndarray],
    ) -> str:
        """Return activity label for one tracked person."""
        zone_map = {
            "mentoring": "mentoring",
            "presenting": "presenting",
            "networking": "networking",
            "sponsor": "sponsor_engagement",
            "food": "eating",
            "rest": "resting",
        }
        if zone_type in zone_map:
            return zone_map[zone_type]

        if zone_type != "coding" or keypoints is None or keypoints.shape[0] < 13:
            return "idle"

        kp = keypoints
        n_kpts = kp.shape[0]

        if n_kpts < 17:
            return "coding" if zone_type == "coding" else "idle"

        def valid(idx: int) -> bool:
            if idx >= n_kpts:
                return False
            return float(kp[idx, 2]) > 0.3 if kp.shape[1] >= 3 else True

        if not all(valid(i) for i in (_L_WRIST, _R_WRIST, _L_SHOULDER, _R_SHOULDER)):
            return "idle"

        lw_y, rw_y = float(kp[_L_WRIST, 1]), float(kp[_R_WRIST, 1])
        ls_y, rs_y = float(kp[_L_SHOULDER, 1]), float(kp[_R_SHOULDER, 1])
        shoulder_y = (ls_y + rs_y) / 2.0
        lw_x, rw_x = float(kp[_L_WRIST, 0]), float(kp[_R_WRIST, 0])
        ls_x, rs_x = float(kp[_L_SHOULDER, 0]), float(kp[_R_SHOULDER, 0])
        shoulder_w = abs(rs_x - ls_x) + 1e-6

        wrists_below_shoulders = lw_y > shoulder_y and rw_y > shoulder_y
        wrists_in_shoulder_width = abs(lw_x - rw_x) < shoulder_w * 1.5

        if valid(_L_HIP) and valid(_R_HIP):
            hip_y = (float(kp[_L_HIP, 1]) + float(kp[_R_HIP, 1])) / 2.0
            if lw_y > hip_y and rw_y > hip_y:
                self._prev_keypoints.pop(track_id, None)
                return "idle"

        prev = self._prev_keypoints.get(track_id)
        if prev is not None and prev.shape == kp.shape:
            motion = float(np.linalg.norm(kp[:, :2] - prev[:, :2]))
            if motion > 15.0 and abs(lw_x - rw_x) > shoulder_w * 0.8:
                self._prev_keypoints[track_id] = kp.copy()
                return "collaborating"

        self._prev_keypoints[track_id] = kp.copy()

        if wrists_below_shoulders and wrists_in_shoulder_width:
            return "coding"
        return "idle"

    def drop_track(self, track_id: int) -> None:
        self._prev_keypoints.pop(track_id, None)
