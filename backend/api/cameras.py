"""Camera list and MJPEG stream endpoints."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Annotated, AsyncGenerator, Optional

import cv2
import numpy as np
import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import CurrentUser, require_role
from backend.api.schemas import CameraResponse
from backend.config import get_settings
from backend.db.database import get_db
from backend.db.models import Camera
from backend.db.redis_sync import get_camera_frame
from backend.middleware.rate_limit import limiter

router = APIRouter(prefix="/api/v1", tags=["cameras"])
settings = get_settings()

_last_frame_cache: dict[str, bytes] = {}
_offline_jpeg: Optional[bytes] = None


def _offline_jpeg_bytes() -> bytes:
    global _offline_jpeg
    if _offline_jpeg is not None:
        return _offline_jpeg
    path = Path(__file__).resolve().parents[2] / "static" / "camera-offline.jpg"
    if path.exists():
        _offline_jpeg = path.read_bytes()
        return _offline_jpeg
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(img, "Camera Offline", (160, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (200, 200, 200), 2)
    _, buf = cv2.imencode(".jpg", img)
    _offline_jpeg = buf.tobytes()
    return _offline_jpeg


@router.get("/cameras")
async def list_cameras(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
) -> dict:
    """List cameras grouped by floor from DB with YAML fallback."""
    rows = (await db.execute(select(Camera).where(Camera.is_active.is_(True)))).scalars().all()
    if rows:
        cameras = [
            CameraResponse(
                id=c.id,
                name=c.name,
                floor=c.floor,
                rtsp_url=c.rtsp_url,
                is_active=c.is_active,
            )
            for c in rows
        ]
    else:
        configs_dir = Path(settings.CONFIGS_DIR)
        if not configs_dir.exists():
            configs_dir = Path(__file__).resolve().parents[2] / "configs"
        cameras_yaml = configs_dir / "cameras.yaml"
        data = yaml.safe_load(cameras_yaml.read_text(encoding="utf-8")) if cameras_yaml.exists() else {}
        cameras = [
            CameraResponse(
                id=c["id"],
                name=c.get("name"),
                floor=c.get("floor"),
                rtsp_url=c.get("rtsp_url"),
                is_active=True,
            )
            for c in data.get("cameras", [])
        ]
    by_floor: dict[int, list] = {}
    for cam in cameras:
        floor = cam.floor if cam.floor is not None else 0
        by_floor.setdefault(floor, []).append(cam.model_dump())
    return {"data": {"cameras": [c.model_dump() for c in cameras], "by_floor": by_floor}}


async def _mjpeg_generator(camera_id: str) -> AsyncGenerator[bytes, None]:
    """Yield MJPEG frames from Redis."""
    boundary = b"--frame"
    while True:
        frame = get_camera_frame(camera_id)
        if frame is None:
            frame = _last_frame_cache.get(camera_id) or _offline_jpeg_bytes()
        else:
            _last_frame_cache[camera_id] = frame
        yield boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        await asyncio.sleep(0.1)


@router.get("/stream/{camera_id}")
@limiter.exempt
async def stream_camera(
    request: Request,
    camera_id: str,
    user: CurrentUser = Depends(require_role(["admin", "operator"])),
) -> StreamingResponse:
    """MJPEG stream for CCTV wall."""
    return StreamingResponse(
        _mjpeg_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
