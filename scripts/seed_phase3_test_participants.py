#!/usr/bin/env python3
"""Register test participants using portrait photos downloaded from the internet."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import cv2
import httpx
import numpy as np
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES_DIR = ROOT / "data" / "face_fixtures"
API_BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
TARGET_COUNT = int(os.environ.get("SEED_PARTICIPANT_COUNT", "5"))

HTTP_HEADERS = {"User-Agent": "SpatialScore-Seed/1.0 (synthetic test data)"}


def _download_jpeg(client: httpx.Client, url: str) -> bytes | None:
    """Download a JPEG and validate magic bytes."""
    try:
        resp = client.get(url, headers=HTTP_HEADERS)
        resp.raise_for_status()
        if resp.content[:2] != b"\xff\xd8":
            logger.warning(f"URL did not return JPEG: {url}")
            return None
        return resp.content
    except Exception as exc:
        logger.warning(f"Download failed for {url}: {exc}")
        return None


def _fetch_randomuser_portraits(count: int) -> list[bytes]:
    """Fetch distinct portrait photos via randomuser.me API."""
    images: list[bytes] = []
    api_url = f"https://randomuser.me/api/?results={count}&inc=picture,nat"
    with httpx.Client(timeout=60, follow_redirects=True, headers=HTTP_HEADERS) as client:
        try:
            resp = client.get(api_url)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as exc:
            logger.warning(f"randomuser.me API failed: {exc}")
            return images

        for i, person in enumerate(results):
            picture = person.get("picture", {})
            for size_key in ("large", "medium", "thumbnail"):
                url = picture.get(size_key)
                if not url:
                    continue
                jpeg = _download_jpeg(client, url)
                if jpeg is not None:
                    cache = FIXTURES_DIR / f"randomuser_{i}_{size_key}.jpg"
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_bytes(jpeg)
                    images.append(jpeg)
                    logger.info(f"Downloaded randomuser portrait {i + 1}/{count}")
                    break
    return images


def _fetch_synthetic_faces(count: int) -> list[bytes]:
    """Fallback: one face per request from thispersondoesnotexist.com."""
    images: list[bytes] = []
    with httpx.Client(timeout=60, follow_redirects=True, headers=HTTP_HEADERS) as client:
        for i in range(count):
            jpeg = _download_jpeg(client, "https://thispersondoesnotexist.com/")
            if jpeg is not None:
                cache = FIXTURES_DIR / f"synthetic_{i}.jpg"
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(jpeg)
                images.append(jpeg)
                logger.info(f"Downloaded synthetic face {i + 1}/{count}")
    return images


def _download_portraits(count: int) -> list[bytes]:
    """Download `count` portrait JPEGs from the internet."""
    images = _fetch_randomuser_portraits(count)
    if len(images) < count:
        need = count - len(images)
        logger.info(f"Fetching {need} synthetic fallback faces")
        images.extend(_fetch_synthetic_faces(need))
    return images


def _load_face_fixtures(count: int) -> list[bytes]:
    """Download up to `count` distinct internet portrait JPEGs."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    cached = sorted(FIXTURES_DIR.glob("*.jpg"))
    if len(cached) >= count and os.environ.get("SEED_FORCE_DOWNLOAD", "").lower() not in ("1", "true", "yes"):
        logger.info(f"Using {count} cached face fixtures from {FIXTURES_DIR}")
        return [p.read_bytes() for p in cached[:count]]

    return _download_portraits(count)[:count]


def _single_face_jpeg(jpeg: bytes) -> bytes | None:
    """Crop to the highest-confidence face so registration accepts the photo."""
    try:
        from backend.core.face_detector import FaceDetector
    except ImportError:
        return jpeg

    frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return None
    detector = FaceDetector()
    faces = detector.detect(frame, threshold=0.5)
    if not faces:
        return None
    face = faces[0]
    x1, y1, x2, y2 = [int(v) for v in face.bbox]
    pad = int(0.25 * max(x2 - x1, y2 - y1, 1))
    h, w = frame.shape[:2]
    y1 = max(0, y1 - pad)
    x1 = max(0, x1 - pad)
    y2 = min(h, y2 + pad)
    x2 = min(w, x2 + pad)
    crop = frame[y1:y2, x1:x2]
    ok, buf = cv2.imencode(".jpg", crop)
    return buf.tobytes() if ok else None


def _register_one(client: httpx.Client, headers: dict[str, str], jpeg: bytes, index: int) -> bool:
    prepared = _single_face_jpeg(jpeg)
    if prepared is None:
        logger.warning(f"Registration {index}: no detectable face after crop")
        return False
    suffix = uuid.uuid4().hex[:6]
    resp = client.post(
        "/api/v1/register",
        headers=headers,
        data={
            "name": f"Phase3 Test {suffix}",
            "team_name": f"Team {index + 1}",
            "track": "ai_ml",
            "consent_confirmed": "true",
        },
        files={"photo": (f"face_{index}.jpg", prepared, "image/jpeg")},
    )
    if resp.status_code in (200, 201):
        body = resp.json().get("data", {})
        pid = body.get("participant_id") or body.get("id", "?")
        logger.info(f"Registered participant {pid}")
        return True
    logger.warning(f"Registration {index} failed: {resp.status_code} {resp.text[:200]}")
    return False


def main() -> None:
    force = os.environ.get("SEED_FORCE_DOWNLOAD", "").lower() in ("1", "true", "yes")
    if force and FIXTURES_DIR.exists():
        for path in FIXTURES_DIR.glob("*.jpg"):
            path.unlink(missing_ok=True)

    frames = _load_face_fixtures(TARGET_COUNT)
    if not frames:
        logger.error("No portrait photos downloaded — check network access from this host")
        sys.exit(1)

    with httpx.Client(base_url=API_BASE, timeout=120) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
        )
        if login.status_code != 200:
            logger.error(f"Login failed: {login.status_code} {login.text}")
            sys.exit(1)
        token = login.json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}

        registered = 0
        attempts = 0
        max_attempts = TARGET_COUNT * 3
        photo_iter = iter(_load_face_fixtures(TARGET_COUNT * 2))
        extra_pool: list[bytes] = []

        while registered < TARGET_COUNT and attempts < max_attempts:
            attempts += 1
            try:
                jpeg = next(photo_iter)
            except StopIteration:
                extra_pool.extend(_download_portraits(3))
                if not extra_pool:
                    break
                jpeg = extra_pool.pop(0)

            if _register_one(client, headers, jpeg, registered):
                registered += 1

    logger.info(f"Registered {registered}/{TARGET_COUNT} participants")
    if registered < TARGET_COUNT:
        logger.warning(f"Only registered {registered} of {TARGET_COUNT} — identity linking may be limited")
    if registered == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
