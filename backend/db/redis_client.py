"""Async Redis client wrappers."""

import json
from typing import Any, Optional

import redis.asyncio as aioredis
from fastapi import Request

from backend.config import get_settings

settings = get_settings()
_redis_pool: Optional[aioredis.Redis] = None

ACTIVITY_STREAM = "activity_stream"
ACTIVITY_STREAM_MAXLEN = 50000


async def init_redis() -> aioredis.Redis:
    """Create shared Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_pool


async def close_redis() -> None:
    """Close Redis pool on shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None


async def get_redis() -> aioredis.Redis:
    """FastAPI dependency for Redis client."""
    return await init_redis()


async def update_leaderboard(participant_id: str, score: float) -> None:
    """ZADD leaderboard sorted set."""
    r = await init_redis()
    await r.zadd("leaderboard", {participant_id: score})


async def get_leaderboard(limit: int = 50) -> list[tuple[str, float]]:
    """ZREVRANGE with scores."""
    r = await init_redis()
    results = await r.zrevrange("leaderboard", 0, limit - 1, withscores=True)
    return [(member, float(score)) for member, score in results]


async def update_participant_state(
    participant_id: str,
    zone: str,
    activity: str,
    score: float,
    last_seen: Optional[str] = None,
) -> None:
    """HSET participant state hash."""
    r = await init_redis()
    mapping: dict[str, str] = {
        "zone": zone,
        "activity": activity,
        "score": str(score),
    }
    if last_seen:
        mapping["last_seen"] = last_seen
    await r.hset(f"participant:{participant_id}", mapping=mapping)


async def get_participant_state(participant_id: str) -> dict[str, str]:
    """HGETALL participant state."""
    r = await init_redis()
    return await r.hgetall(f"participant:{participant_id}")


async def update_zone_occupancy(zone_name: str, count: int) -> None:
    """HSET zone occupancy count."""
    r = await init_redis()
    await r.hset("zone_occupancy", zone_name, count)


async def get_zone_occupancy() -> dict[str, str]:
    """HGETALL zone occupancy."""
    r = await init_redis()
    return await r.hgetall("zone_occupancy")


async def push_activity_event(event: dict[str, Any]) -> str:
    """XADD to activity_stream with MAXLEN trim."""
    r = await init_redis()
    flat = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in event.items()}
    return await r.xadd(ACTIVITY_STREAM, flat, maxlen=ACTIVITY_STREAM_MAXLEN, approximate=True)


async def read_activity_events(last_id: str = "0", count: int = 100) -> list[dict[str, Any]]:
    """Read recent entries from activity_stream via XRANGE."""
    r = await init_redis()
    start = "-" if last_id in ("0", "0-0") else f"({last_id}"
    messages = await r.xrange(ACTIVITY_STREAM, min=start, max="+", count=count)
    events: list[dict[str, Any]] = []
    for msg_id, fields in messages:
        parsed: dict[str, Any] = {"id": msg_id}
        for key, value in fields.items():
            try:
                parsed[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                parsed[key] = value
        events.append(parsed)
    return events


async def get_stream_length() -> int:
    """XLEN activity_stream."""
    r = await init_redis()
    return int(await r.xlen(ACTIVITY_STREAM))


async def get_camera_statuses() -> dict[str, dict[str, str]]:
    """HGETALL for each camera_status:* key."""
    r = await init_redis()
    statuses: dict[str, dict[str, str]] = {}
    async for key in r.scan_iter(match="camera_status:*"):
        cam_id = key.split(":", 1)[-1]
        statuses[cam_id] = await r.hgetall(key)
    return statuses


async def get_heatmap_current() -> Optional[dict[str, Any]]:
    """GET heatmap:current parsed JSON."""
    r = await init_redis()
    raw = await r.get("heatmap:current")
    if not raw:
        return None
    return json.loads(raw)


async def publish_zones_updated() -> None:
    r = await init_redis()
    await r.publish("zones_updated", "1")


async def publish_scoring_config_updated() -> None:
    r = await init_redis()
    await r.publish("scoring_config_updated", "1")


async def invalidate_leaderboard_cache() -> None:
    """Delete all leaderboard_cache:* keys."""
    r = await init_redis()
    async for key in r.scan_iter("leaderboard_cache:*"):
        await r.delete(key)
