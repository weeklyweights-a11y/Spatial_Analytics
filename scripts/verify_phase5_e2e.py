#!/usr/bin/env python3
"""Smoke verification for Phase 5 sponsor reports and exports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 5 API endpoints")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", required=True, help="Admin JWT bearer token")
    args = parser.parse_args()

    headers = {"Authorization": f"Bearer {args.token}"}
    client = httpx.Client(base_url=args.base_url, headers=headers, timeout=60.0)
    ok = 0
    fail = 0

    def check(name: str, resp: httpx.Response, expect: int = 200) -> None:
        nonlocal ok, fail
        if resp.status_code == expect:
            print(f"PASS {name} ({resp.status_code})")
            ok += 1
        else:
            print(f"FAIL {name} ({resp.status_code}): {resp.text[:200]}")
            fail += 1

    r = client.get("/api/v1/sponsors")
    check("sponsors list", r)
    sponsors = r.json().get("data", []) if r.status_code == 200 else []
    if sponsors:
        sid = sponsors[0]["id"]
        r = client.get(f"/api/v1/sponsors/{sid}/report")
        check("sponsor report JSON", r)
        if r.status_code == 200:
            metrics = r.json()["data"]["metrics"]
            for key in (
                "unique_visitors",
                "total_visits",
                "avg_dwell_seconds",
                "median_dwell_seconds",
                "return_visitors",
                "return_rate_pct",
                "peak_hour",
                "total_dwell_minutes",
            ):
                if key in metrics:
                    ok += 0
                else:
                    print(f"FAIL missing metric key: {key}")
                    fail += 1
        r = client.get(f"/api/v1/sponsors/{sid}/report/pdf")
        check("sponsor PDF", r)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            print("PASS PDF magic bytes")
            ok += 1
        else:
            print("FAIL PDF magic bytes")
            fail += 1

    r = client.get("/api/v1/export/scores")
    check("export scores", r)
    if r.status_code == 200 and "participant_id" in r.text:
        print("PASS scores CSV header")
        ok += 1

    r = client.get("/api/v1/export/scores", headers={"Authorization": "Bearer invalid"})
    if r.status_code in (401, 403):
        print("PASS export rejects bad token")
        ok += 1

    print(f"\n{ok} passed, {fail} failed")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
