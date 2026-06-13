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


def read_activity_events(last_id: str = "0", count: int = 100) -> list[dict[str, Any]]:
    """XREAD from activity_stream; parse JSON-encoded list/dict fields."""
    r = get_sync_redis()
    result = r.xread({ACTIVITY_STREAM: last_id}, count=count, block=0)
    events: list[dict[str, Any]] = []
    for _stream, messages in result:
        for msg_id, fields in messages:
            parsed: dict[str, Any] = {"id": msg_id}
            for key, value in fields.items():
                parsed[key] = _parse_redis_field(value)
            events.append(parsed)
    return events


def _parse_redis_field(value: str) -> Any:
    """Decode stream field values written by push_activity_event."""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def get_camera_status(camera_id: str) -> dict[str, str]:
    """HGETALL camera_status:{camera_id}."""
    r = get_sync_redis()
    return r.hgetall(f"camera_status:{camera_id}")


def get_camera_frame(camera_id: str) -> Optional[bytes]:
    """GET camera_frame:{camera_id} JPEG bytes."""
    r = get_sync_redis_binary()
    data = r.get(f"camera_frame:{camera_id}")
    return data if data else None


def get_camera_frame_ttl(camera_id: str) -> int:
    """TTL seconds for camera_frame:{camera_id}."""
    r = get_sync_redis_binary()
    return int(r.ttl(f"camera_frame:{camera_id}"))


def get_zone_occupancy() -> dict[str, str]:
    """HGETALL zone_occupancy."""
    r = get_sync_redis()
    return r.hgetall("zone_occupancy")


EVENT_FIELD_NAMES = frozenset(
    {
        "participant_id",
        "camera_id",
        "zone",
        "zone_type",
        "activity",
        "track_id",
        "bbox",
        "confidence",
        "timestamp",
    }
)


def validate_activity_event(event: dict[str, Any]) -> None:
    """Raise AssertionError if required activity event fields are missing."""
    missing = EVENT_FIELD_NAMES - set(event.keys())
    if missing:
        raise AssertionError(f"Activity event missing fields: {sorted(missing)}")


def close_sync_redis() -> None:
    global _redis_text, _redis_bin
    if _redis_text is not None:
        _redis_text.close()
        _redis_text = None
    if _redis_bin is not None:
        _redis_bin.close()
        _redis_bin = None
