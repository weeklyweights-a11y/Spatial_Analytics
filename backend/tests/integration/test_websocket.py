"""Integration tests for WebSocket channels."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.api.deps import create_access_token
from backend.main import create_app


@pytest.fixture
def ws_app(face_matcher):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _noop(_app):
        yield

    app = create_app()
    app.router.lifespan_context = _noop
    app.state.face_matcher = face_matcher
    app.state.start_time = __import__("time").time()
    return app


def test_ws_leaderboard_requires_auth(ws_app):
    client = TestClient(ws_app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/leaderboard"):
            pass


def test_ws_leaderboard_accepts_token(ws_app):
    token = create_access_token("testadmin", "admin", datetime.now(timezone.utc) + timedelta(hours=1))
    payload = {
        "type": "leaderboard",
        "data": [],
        "total_participants": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    client = TestClient(ws_app)
    with patch(
        "backend.api.websocket._leaderboard_payload",
        new=AsyncMock(return_value=payload),
    ):
        with client.websocket_connect(f"/ws/leaderboard?token={token}") as ws:
            msg = ws.receive_text()
            assert "leaderboard" in msg


def test_ws_tracking_rejects_viewer(ws_app):
    token = create_access_token("testviewer", "viewer", datetime.now(timezone.utc) + timedelta(hours=1))
    client = TestClient(ws_app)
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/tracking/CAM-01?token={token}"):
            pass
    assert exc_info.value.code == 4003
