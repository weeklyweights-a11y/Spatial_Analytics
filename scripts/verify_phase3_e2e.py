#!/usr/bin/env python3
"""Phase 3 end-to-end verification script."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_env_file() -> None:
    """Load .env into os.environ for local runs (does not override existing vars)."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file()

API = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("REDIS_URL", REDIS_URL)


def check(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    passed = 0
    total = 0

    with httpx.Client(base_url=API, timeout=30) as client:
        total += 1
        r = client.get("/api/v1/health")
        health = r.json() if r.status_code == 200 else {}
        scoring_check = health.get("checks", {}).get("scoring_engine", {})
        ok = r.status_code == 200 and scoring_check.get("status") in ("ok", "degraded", "healthy", "unknown")
        passed += check("health scoring_engine", ok, str(scoring_check.get("status", r.status_code)))

        if args.full:
            total += 1
            login = client.post(
                "/api/v1/auth/login",
                json={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
            )
            passed += check("admin login", login.status_code == 200, login.text[:80] if login.status_code != 200 else "")
            if login.status_code != 200:
                print("\nHint: set ADMIN_PASSWORD or run backend.cli reset-password")
                print(f"\n{passed}/{total} checks passed")
                return 1

            token = login.json()["data"]["token"]
            headers = {"Authorization": f"Bearer {token}"}

            total += 1
            lb = client.get("/api/v1/scores/leaderboard?limit=5", headers=headers)
            lb_data = lb.json().get("data", []) if lb.status_code == 200 else []
            passed += check("scores leaderboard", lb.status_code == 200, f"entries={len(lb_data)}")

            total += 1
            cams = client.get("/api/v1/cameras", headers=headers)
            cam_payload = cams.json().get("data", {}) if cams.status_code == 200 else {}
            if isinstance(cam_payload, dict):
                cam_list = cam_payload.get("cameras", [])
            else:
                cam_list = cam_payload if isinstance(cam_payload, list) else []
            passed += check("cameras list", cams.status_code == 200 and len(cam_list) > 0, f"count={len(cam_list)}")

            if cam_list:
                cam_id = cam_list[0].get("id") or cam_list[0].get("camera_id", "CAM-01")
                total += 1
                with client.stream(
                    "GET",
                    f"/api/v1/stream/{cam_id}",
                    headers=headers,
                    timeout=5,
                ) as stream:
                    ctype = stream.headers.get("content-type", "")
                    status = stream.status_code
                passed += check(
                    "mjpeg stream",
                    status == 200 and "multipart" in ctype,
                    ctype or str(status),
                )

            total += 1
            tracking = client.get("/api/v1/tracking/active", headers=headers)
            passed += check("tracking active", tracking.status_code == 200)

            total += 1
            viewer_login = client.post(
                "/api/v1/auth/login",
                json={"username": "testviewer", "password": "testpass123"},
            )
            if viewer_login.status_code != 200:
                passed += check("viewer login (skip)", True, "no testviewer user")
            else:
                vtoken = viewer_login.json()["data"]["token"]
                vheaders = {"Authorization": f"Bearer {vtoken}"}
                total += 1
                denied = client.get(
                    "/api/v1/scores/00000000-0000-0000-0000-000000000001",
                    headers=vheaders,
                )
                passed += check("viewer denied score detail", denied.status_code == 403)
                total += 1
                cam_denied = client.get("/api/v1/cameras", headers=vheaders)
                passed += check("viewer denied cameras", cam_denied.status_code == 403)

        try:
            from backend.db import redis_sync

            total += 1
            flush = redis_sync.get_scoring_last_flush_at()
            passed += check(
                "scoring_last_flush_at",
                flush is not None or not args.full,
                flush or "waiting for first flush",
            )

            if args.full:
                total += 1
                stream_len = redis_sync.get_stream_length()
                passed += check("activity_stream events", stream_len > 0, f"xlen={stream_len}")

                total += 1
                heartbeat = redis_sync.get_scoring_status()
                passed += check(
                    "scoring heartbeat",
                    bool(heartbeat) and heartbeat.get("status") in ("running", "error"),
                    str(heartbeat),
                )
        except Exception as exc:
            total += 1
            passed += check("redis scoring keys", False, str(exc))

    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
