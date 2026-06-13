"""Synchronous Redis client for camera workers."""

from __future__ import annotations

import json
from typing import Any, Optional

import redis

from backend.config import get_settings
from backend.db.redis_client import ACTIVITY_STREAM, ACTIVITY_STREAM_MAXLEN

_redis_text: Optional[redis.Redis] = None
_redis_bin: Optional[redis.Redis] = None


def get_sync_redis() -> redis.Redis:
    """Text Redis client for streams and hashes."""
    global _redis_text
    if _redis_text is None:
        settings = get_settings()
        _redis_text = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_text


def get_sync_redis_binary() -> redis.Redis:
    """Binary Redis client for JPEG frame blobs."""
    global _redis_bin
    if _redis_bin is None:
        settings = get_settings()
        _redis_bin = redis.from_url(settings.REDIS_URL, decode_responses=False)
    return _redis_bin


def push_activity_event(event: dict[str, Any]) -> str:
    """XADD to activity_stream with MAXLEN trim."""
    r = get_sync_redis()
    flat = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in event.items()}
    return r.xadd(ACTIVITY_STREAM, flat, maxlen=ACTIVITY_STREAM_MAXLEN, approximate=True)


def update_zone_occupancy(zone_name: str, count: int) -> None:
    r = get_sync_redis()
    r.hset("zone_occupancy", zone_name, count)


def set_camera_heartbeat(camera_id: str, fields: dict[str, Any]) -> None:
    r = get_sync_redis()
    mapping = {k: str(v) for k, v in fields.items()}
    r.hset(f"camera_status:{camera_id}", mapping=mapping)


def set_camera_frame(camera_id: str, jpeg_bytes: bytes, ttl_seconds: int = 5) -> None:
    r = get_sync_redis_binary()
    key = f"camera_frame:{camera_id}"
    r.set(key, jpeg_bytes)
    r.expire(key, ttl_seconds)


def get_stream_length() -> int:
    r = get_sync_redis()
    return int(r.xlen(ACTIVITY_STREAM))


def close_sync_redis() -> None:
    global _redis_text, _redis_bin
    if _redis_text is not None:
        _redis_text.close()
        _redis_text = None
    if _redis_bin is not None:
        _redis_bin.close()
        _redis_bin = None
