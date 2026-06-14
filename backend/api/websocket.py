"""WebSocket channels for live dashboard updates."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Cookie, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select

from backend.api.deps import ALGORITHM, _decode_token
from backend.api.ws_manager import ws_manager
from backend.config import get_settings
from backend.db.database import AsyncSessionLocal
from backend.db.models import Participant, Score
from backend.db.redis_client import get_leaderboard, get_participant_state, get_redis, init_redis

router = APIRouter(tags=["websocket"])
settings = get_settings()


def _auth_ws(
    token: Optional[str],
    cookie_token: Optional[str],
) -> dict:
    raw = token or cookie_token
    if not raw:
        raise WebSocketDisconnect(code=4001)
    try:
        return _decode_token(raw)
    except HTTPException as exc:
        raise WebSocketDisconnect(code=4001) from exc


async def _leaderboard_payload() -> dict:
    redis = await get_redis()
    rows = await get_leaderboard(limit=50)
    total = await redis.scard("leaderboard") if False else None
    async with AsyncSessionLocal() as db:
        total_participants = await db.scalar(
            select(func.count()).select_from(Participant).where(Participant.opted_out.is_(False))
        )
        entries = []
        for pid, score_val in rows[:50]:
            result = await db.execute(
                select(Participant, Score)
                .join(Score, Score.participant_id == Participant.id, isouter=True)
                .where(Participant.id == UUID(pid))
            )
            row = result.first()
            if not row:
                continue
            participant, score = row
            state = await get_participant_state(pid)
            entries.append(
                {
                    "participant_id": pid,
                    "name": participant.name,
                    "team_name": participant.team_name,
                    "total_score": float(score_val),
                    "rank": score.rank if score else None,
                    "current_activity": state.get("activity"),
                    "current_zone": state.get("zone"),
                    "tags": list(score.tags or []) if score else [],
                }
            )
    return {
        "type": "leaderboard",
        "data": entries,
        "total_participants": total_participants or 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.websocket("/ws/leaderboard")
async def ws_leaderboard(
    websocket: WebSocket,
    token: Annotated[Optional[str], Query()] = None,
    access_token: Annotated[Optional[str], Cookie(alias=settings.JWT_COOKIE_NAME)] = None,
) -> None:
    """Push leaderboard every 30s — all authenticated roles."""
    payload_data = _auth_ws(token, access_token)
    role = payload_data.get("role", "viewer")
    if role not in ("admin", "operator", "viewer"):
        await websocket.close(code=4003)
        return
    channel = "leaderboard"
    if not await ws_manager.connect(channel, websocket):
        await websocket.close(code=4003)
        return
    try:
        while True:
            await websocket.send_text(json.dumps(await _leaderboard_payload(), default=str))
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(channel, websocket)


@router.websocket("/ws/tracking/{camera_id}")
async def ws_tracking(
    websocket: WebSocket,
    camera_id: str,
    token: Annotated[Optional[str], Query()] = None,
    access_token: Annotated[Optional[str], Cookie(alias=settings.JWT_COOKIE_NAME)] = None,
) -> None:
    """Forward tracking pub/sub — admin/operator only."""
    payload_data = _auth_ws(token, access_token)
    if payload_data.get("role") not in ("admin", "operator"):
        await websocket.close(code=4003)
        return
    channel = f"tracking:{camera_id}"
    if not await ws_manager.connect(channel, websocket):
        await websocket.close(code=4003)
        return
    redis = await init_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = message["data"]
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            await websocket.send_text(data)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await ws_manager.disconnect(channel, websocket)


@router.websocket("/ws/participant/{participant_id}")
async def ws_participant(
    websocket: WebSocket,
    participant_id: str,
    token: Annotated[Optional[str], Query()] = None,
    access_token: Annotated[Optional[str], Cookie(alias=settings.JWT_COOKIE_NAME)] = None,
) -> None:
    """Live participant updates — admin/operator only."""
    payload_data = _auth_ws(token, access_token)
    if payload_data.get("role") not in ("admin", "operator"):
        await websocket.close(code=4003)
        return
    channel = f"participant:{participant_id}"
    if not await ws_manager.connect(channel, websocket):
        await websocket.close(code=4003)
        return
    try:
        while True:
            state = await get_participant_state(participant_id)
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Participant, Score)
                    .join(Score, Score.participant_id == Participant.id, isouter=True)
                    .where(Participant.id == UUID(participant_id))
                )
                row = result.first()
            name = row[0].name if row else ""
            score_row = row[1] if row else None
            payload = {
                "type": "participant_update",
                "participant_id": participant_id,
                "name": name,
                "zone": state.get("zone"),
                "activity": state.get("activity"),
                "score": float(state.get("score", 0) or 0),
                "rank": score_row.rank if score_row else None,
                "tags": list(score_row.tags or []) if score_row else [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await websocket.send_text(json.dumps(payload, default=str))
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(channel, websocket)


@router.websocket("/ws/alerts")
async def ws_alerts(
    websocket: WebSocket,
    token: Annotated[Optional[str], Query()] = None,
    access_token: Annotated[Optional[str], Cookie(alias=settings.JWT_COOKIE_NAME)] = None,
) -> None:
    """Placeholder alerts channel until Phase 4."""
    _auth_ws(token, access_token)
    channel = "alerts"
    if not await ws_manager.connect(channel, websocket):
        await websocket.close(code=4003)
        return
    try:
        while True:
            await websocket.send_text(
                json.dumps({"type": "alerts", "data": [], "message": "No alerts"})
            )
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(channel, websocket)


async def scores_updated_subscriber() -> None:
    """Background task: broadcast leaderboard refresh on scores_updated."""
    redis = await init_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe("scores_updated")
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        payload = await _leaderboard_payload()
        await ws_manager.broadcast("leaderboard", payload)
