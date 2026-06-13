#!/usr/bin/env python3
"""Quick probe for VM worker pipeline (run via docker compose exec)."""

from __future__ import annotations

import time

import cv2
import redis

from backend.config import get_settings
from backend.core.person_detector import PersonDetector
from backend.db import redis_sync


def main() -> None:
    settings = get_settings()
    print(f"REDIS_URL={settings.REDIS_URL}")

    r = redis.from_url(settings.REDIS_URL)
    print(f"redis ping={r.ping()}")

    cap = cv2.VideoCapture("rtsp://mediamtx:8554/cam01")
    ok, frame = cap.read()
    cap.release()
    print(f"rtsp frame ok={ok} shape={frame.shape if ok else None}")

    detector = PersonDetector()
    t0 = time.time()
    boxes, scores, keypoints = detector.detect(frame)
    dt = time.time() - t0
    print(f"detect count={len(boxes)} elapsed={dt:.2f}s")
    if len(boxes):
        print(f"sample box={boxes[0]} score={scores[0]}")
        print(f"box min={boxes.min():.2f} max={boxes.max():.2f}")

    redis_sync.set_camera_heartbeat(
        "CAM-01",
        {"status": "probe", "frames_processed": 1, "fps": "0.1"},
    )
    _, jpeg = cv2.imencode(".jpg", frame)
    redis_sync.set_camera_frame("CAM-01", jpeg.tobytes(), ttl_seconds=30)
    print("wrote camera_status and camera_frame probe keys")


if __name__ == "__main__":
    main()
