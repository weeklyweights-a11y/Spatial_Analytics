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
    """Read recent entries from activity_stream; parse JSON-encoded list/dict fields."""
    r = get_sync_redis()
    start = "-" if last_id in ("0", "0-0") else f"({last_id}"
    messages = r.xrange(ACTIVITY_STREAM, min=start, max="+", count=count)
    events: list[dict[str, Any]] = []
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


SCORING_LAST_ID_KEY = "scoring_last_id"
SCORING_LAST_FLUSH_KEY = "scoring_last_flush_at"
SCORING_STATUS_KEY = "scoring_status"
SCORES_UPDATED_CHANNEL = "scores_updated"


def get_scoring_last_id() -> Optional[str]:
    r = get_sync_redis()
    val = r.get(SCORING_LAST_ID_KEY)
    return val if val else None


def set_scoring_last_id(msg_id: str) -> None:
    r = get_sync_redis()
    r.set(SCORING_LAST_ID_KEY, msg_id)


def set_scoring_last_flush_at(iso_ts: str) -> None:
    r = get_sync_redis()
    r.set(SCORING_LAST_FLUSH_KEY, iso_ts)


def set_scoring_heartbeat(
    last_flush_at: str,
    last_duration_ms: int,
    events_processed: int,
    status: str,
) -> None:
    r = get_sync_redis()
    r.hset(
        SCORING_STATUS_KEY,
        mapping={
            "last_flush_at": last_flush_at,
            "last_duration_ms": str(last_duration_ms),
            "events_processed": str(events_processed),
            "status": status,
        },
    )


def publish_scores_updated() -> None:
    r = get_sync_redis()
    r.publish(SCORES_UPDATED_CHANNEL, "1")


def publish_tracking_update(camera_id: str, payload: dict[str, Any]) -> None:
    r = get_sync_redis()
    r.publish(f"tracking:{camera_id}", json.dumps(payload))


def update_participant_state(
    participant_id: str,
    zone: str,
    activity: str,
    score: float,
    last_seen: Optional[str] = None,
) -> None:
    r = get_sync_redis()
    mapping: dict[str, str] = {
        "zone": zone,
        "activity": activity,
        "score": str(score),
    }
    if last_seen:
        mapping["last_seen"] = last_seen
    r.hset(f"participant:{participant_id}", mapping=mapping)


def update_leaderboard_sync(participant_id: str, score: float) -> None:
    r = get_sync_redis()
    r.zadd("leaderboard", {participant_id: score})


def add_visited_zone(participant_id: str, zone_name: str) -> None:
    r = get_sync_redis()
    r.sadd(f"visited_zones:{participant_id}", zone_name)


def visited_zone_count(participant_id: str) -> int:
    r = get_sync_redis()
    return int(r.scard(f"visited_zones:{participant_id}"))


def get_scoring_status() -> dict[str, str]:
    r = get_sync_redis()
    return r.hgetall(SCORING_STATUS_KEY)


def get_scoring_last_flush_at() -> Optional[str]:
    r = get_sync_redis()
    val = r.get(SCORING_LAST_FLUSH_KEY)
    return val if val else None
