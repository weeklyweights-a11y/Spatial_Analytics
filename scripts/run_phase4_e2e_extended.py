#!/usr/bin/env python3
"""Extended Phase 4 E2E checks beyond verify_phase4_e2e.py."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
import websockets

DEFAULT_BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"


def check(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    suffix = f" ({detail})" if detail else ""
    print(f"{status} {name}{suffix}")
    return ok


async def ws_heatmap_check(token: str) -> bool:
    url = f"{WS_BASE}/ws/heatmap?token={token}"
    try:
        async with websockets.connect(url, open_timeout=10) as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(raw)
            return msg.get("type") == "heatmap" and "data" in msg
    except Exception as exc:
        print(f"  ws error: {exc}")
        return False


async def ws_connect_ok(path: str, token: str) -> bool:
    url = f"{WS_BASE}{path}?token={token}"
    try:
        async with websockets.connect(url, open_timeout=10) as ws:
            return True
    except Exception as exc:
        print(f"  ws error: {exc}")
        return False


async def run(base_url: str, token: str) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    passed = 0
    total = 0

    def record(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, total
        total += 1
        if check(name, ok, detail):
            passed += 1

    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=60.0) as client:
        r = await client.get("/api/v1/analytics/heatmap")
        data = r.json().get("data", {})
        zones = data.get("zones", {})
        has_pct = any("pct" in z for z in zones.values()) if zones else False
        record("heatmap zones with pct", r.status_code == 200 and has_pct, f"zones={len(zones)}")

        r = await client.get("/api/v1/config/scoring")
        weights = r.json().get("data", [])
        record("config/scoring GET", r.status_code == 200 and len(weights) > 0, f"count={len(weights)}")

        if weights:
            activity = weights[0]["activity"]
            new_weight = float(weights[0]["weight"]) + 0.1
            r = await client.put(
                "/api/v1/config/scoring",
                json={"weights": [{"activity": activity, "weight": new_weight, "min_dwell_seconds": 120}]},
            )
            record("config/scoring PUT", r.status_code == 200)

        zone_name = f"E2E Zone {uuid.uuid4().hex[:6]}"
        r = await client.post(
            "/api/v1/zones",
            json={
                "name": zone_name,
                "zone_type": "coding",
                "camera_id": "CAM-01",
                "polygon_coords": [[0, 0], [100, 0], [100, 100]],
                "floor_polygon": [[10, 10], [90, 10], [90, 90]],
                "floor": 0,
                "capacity": 25,
            },
        )
        zone_id = r.json().get("data", {}).get("id") if r.status_code == 200 else None
        record("zones POST", r.status_code == 200 and zone_id is not None)

        if zone_id:
            r = await client.put(f"/api/v1/zones/{zone_id}", json={"capacity": 30})
            record("zones PUT", r.status_code == 200 and r.json()["data"]["capacity"] == 30)
            r = await client.delete(f"/api/v1/zones/{zone_id}")
            record("zones DELETE fresh", r.status_code == 200)

        r = await client.get("/api/v1/scores/leaderboard?track=ai_ml&limit=5")
        record("leaderboard track filter", r.status_code == 200)

        r = await client.get("http://localhost:3000/", follow_redirects=True)
        record("dashboard HTTP", r.status_code == 200)

    record("ws/heatmap initial", await ws_heatmap_check(token))
    record("ws/alerts connect", await ws_connect_ok("/ws/alerts", token))

    print(f"\n{passed}/{total} extended checks passed")
    return 0 if passed == total else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    return asyncio.run(run(args.base_url, args.token))


if __name__ == "__main__":
    raise SystemExit(main())
