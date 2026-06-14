"""WebSocket connection manager."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import WebSocket
from loguru import logger


class WSManager:
    """Track active WebSocket connections per channel."""

    MAX_CONNECTIONS = 50

    def __init__(self) -> None:
        self._channels: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, channel: str, websocket: WebSocket) -> bool:
        """Accept connection if under limit."""
        async with self._lock:
            conns = self._channels.setdefault(channel, set())
            if len(conns) >= self.MAX_CONNECTIONS:
                return False
            await websocket.accept()
            conns.add(websocket)
            logger.info(f"WebSocket connected: channel={channel} count={len(conns)}")
            return True

    async def disconnect(self, channel: str, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._channels.get(channel, set())
            conns.discard(websocket)
            logger.info(f"WebSocket disconnected: channel={channel} count={len(conns)}")

    async def broadcast(self, channel: str, payload: dict[str, Any]) -> None:
        """Send JSON to all connections on channel."""
        async with self._lock:
            conns = list(self._channels.get(channel, set()))
        dead: list[WebSocket] = []
        text = json.dumps(payload, default=str)
        for ws in conns:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(channel, ws)

    def connection_count(self, channel: Optional[str] = None) -> int:
        if channel:
            return len(self._channels.get(channel, set()))
        return sum(len(v) for v in self._channels.values())


ws_manager = WSManager()
