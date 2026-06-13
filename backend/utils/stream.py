"""RTSP frame generator with exponential backoff reconnect."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Callable, Optional

import cv2
import numpy as np
from loguru import logger


class StreamReconnectError(Exception):
    """Raised when stream fails persistently."""


def _opencv_frame_generator(rtsp_url: str) -> Iterator[np.ndarray]:
    """Read BGR frames from RTSP via OpenCV (more reliable than sv generator for MediaMTX)."""
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video at {rtsp_url}")
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError(f"RTSP read failed at {rtsp_url}")
            yield frame
    finally:
        cap.release()


def frame_generator_with_reconnect(
    rtsp_url: str,
    on_reconnecting: Optional[Callable[[], None]] = None,
    on_reconnected: Optional[Callable[[float], None]] = None,
    on_persistent_failure: Optional[Callable[[], None]] = None,
    max_retries_before_error: int = 5,
) -> Iterator[np.ndarray]:
    """Yield BGR frames; reconnect with 1s->16s backoff on failure."""
    backoff = 1.0
    max_backoff = 16.0
    retry_count = 0
    disconnect_at: Optional[float] = None

    while True:
        try:
            for frame in _opencv_frame_generator(rtsp_url):
                if disconnect_at is not None and on_reconnected:
                    downtime = time.monotonic() - disconnect_at
                    on_reconnected(downtime)
                    disconnect_at = None
                retry_count = 0
                backoff = 1.0
                yield frame
        except Exception as exc:
            if disconnect_at is None:
                disconnect_at = time.monotonic()
            retry_count += 1
            if on_reconnecting:
                on_reconnecting()
            logger.warning(
                "RTSP stream timeout: retry_count={}, error={}",
                retry_count,
                exc,
            )
            if retry_count >= max_retries_before_error and on_persistent_failure:
                on_persistent_failure()
                logger.error("RTSP stream failed after {} retries", max_retries_before_error)
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
