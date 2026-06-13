#!/usr/bin/env python3
"""Step through one camera-worker frame on the VM."""

from __future__ import annotations

import time
import traceback

import cv2

from backend.workers.camera_worker import CameraWorker


def main() -> None:
    worker = CameraWorker("CAM-01", "rtsp://mediamtx:8554/cam01")
    cap = cv2.VideoCapture(worker.rtsp_url)
    ok, frame = cap.read()
    cap.release()
    print(f"frame ok={ok} shape={None if not ok else frame.shape}")
    if not ok:
        return

    t0 = time.time()
    try:
        worker._process_frame(frame)
        print(f"process_frame ok elapsed={time.time()-t0:.2f}s frames={worker._frames_processed}")
    except Exception:
        print(f"process_frame failed elapsed={time.time()-t0:.2f}s")
        traceback.print_exc()


if __name__ == "__main__":
    main()
