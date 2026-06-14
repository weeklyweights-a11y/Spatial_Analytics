#!/usr/bin/env python3
"""Phase 4 E2E verification script."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx

DEFAULT_BASE = "http://localhost:8000"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 4 endpoints")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    headers = {"Authorization": f"Bearer {args.token}"}
    passed = 0
    failed = 0

    def check(name: str, ok: bool) -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"PASS {name}")
        else:
            failed += 1
            print(f"FAIL {name}")

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=30.0) as client:
        r = client.get("/api/v1/analytics/heatmap")
        check("analytics/heatmap", r.status_code == 200 and "data" in r.json())

        r = client.get("/api/v1/analytics/energy")
        check("analytics/energy defaults", r.status_code == 200 and "points" in r.json().get("data", {}))

        r = client.get("/api/v1/alerts")
        check("alerts list", r.status_code == 200)

        r = client.get("/api/v1/venues/floors")
        check("venues/floors", r.status_code == 200)

        r = client.get("/api/v1/health")
        checks = r.json().get("checks", {})
        check("health heatmap_worker", "heatmap_worker" in checks)

    print(f"\n{passed}/{passed + failed} checks passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
