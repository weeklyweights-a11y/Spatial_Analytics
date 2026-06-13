#!/usr/bin/env python3
"""Automated Phase 2 E2E verification on the GCP VM (or local stack).

Assumes Docker Compose is up with redis, mediamtx, postgres, api, and camera-worker-01.

Usage:
  python scripts/verify_phase2_e2e.py --check-only
  python scripts/verify_phase2_e2e.py --full
  python scripts/verify_phase2_e2e.py --full --start-stream --video test_data/test.mp4

Environment:
  REDIS_URL, MODELS_DIR, TEST_VIDEO_PATH, MEDIAMTX_HOST, TEST_CAMERA_ID
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.db import redis_sync
from backend.tests.integration.pipeline_helpers import (
    deimv2_model_path,
    ffmpeg_available,
    redis_available,
    start_rtmp_simulator,
    test_video_path,
    wait_for,
)


class CheckResult:
    def __init__(self, name: str, passed: bool, detail: str = "") -> None:
        self.name = name
        self.passed = passed
        self.detail = detail


def _check(name: str, ok: bool, detail: str = "") -> CheckResult:
    return CheckResult(name, ok, detail)


def check_prerequisites() -> list[CheckResult]:
    results: list[CheckResult] = []
    deim = deimv2_model_path()
    results.append(_check("DEIMv2 ONNX present", deim.exists(), str(deim)))

    scrfd = Path(os.environ.get("MODELS_DIR", REPO_ROOT / "models")) / "scrfd_10g.onnx"
    arcface = Path(os.environ.get("MODELS_DIR", REPO_ROOT / "models")) / "arcface_r100.onnx"
    results.append(_check("SCRFD ONNX present", scrfd.exists(), str(scrfd)))
    results.append(_check("ArcFace ONNX present", arcface.exists(), str(arcface)))

    video = test_video_path()
    results.append(_check("Test video present", video.exists(), str(video)))

    results.append(_check("ffmpeg available", ffmpeg_available()))
    results.append(_check("Redis reachable", redis_available(), os.environ.get("REDIS_URL", "redis://localhost:6379/0")))

    api_url = os.environ.get("INTEGRATION_API_URL", "http://localhost:8000")
    try:
        with urllib.request.urlopen(f"{api_url}/api/v1/health", timeout=5) as resp:
            body = json.loads(resp.read().decode())
        ok = body.get("status") in {"healthy", "degraded"}
        results.append(_check("API health endpoint", ok, body.get("status", "")))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        results.append(_check("API health endpoint", False, str(exc)))

    faiss_index = Path(os.environ.get("FAISS_INDEX_PATH", REPO_ROOT / "data" / "faiss" / "faiss_index.bin"))
    has_faiss = faiss_index.exists() and faiss_index.stat().st_size > 0
    results.append(
        _check(
            "FAISS index present (optional until registration)",
            True,
            str(faiss_index) if has_faiss else "empty — identity events require registered faces",
        )
    )
    return results


def check_runtime(camera_id: str = "CAM-01", timeout: float = 90.0) -> list[CheckResult]:
    results: list[CheckResult] = []
    redis_sync.close_sync_redis()

    status = redis_sync.get_camera_status(camera_id)
    hb_ok = bool(status.get("last_heartbeat")) and status.get("status") in {"active", "reconnecting", "shutdown"}
    results.append(_check("Camera worker heartbeat", hb_ok, json.dumps(status)))

    frame = redis_sync.get_camera_frame(camera_id)
    ttl = redis_sync.get_camera_frame_ttl(camera_id)
    frame_ok = frame is not None and len(frame or b"") > 1000 and ttl > 0
    results.append(_check("Annotated frame in Redis", frame_ok, f"ttl={ttl}"))

    occupancy = redis_sync.get_zone_occupancy()
    results.append(_check("Zone occupancy hash populated", isinstance(occupancy, dict), json.dumps(occupancy)))

    stream_len = redis_sync.get_stream_length()
    results.append(_check("Activity stream reachable", stream_len >= 0, f"XLEN={stream_len}"))

    events = redis_sync.read_activity_events(count=10)
    identified = [e for e in events if e.get("participant_id")]
    if identified:
        try:
            redis_sync.validate_activity_event(identified[-1])
            results.append(_check("Latest activity event schema valid", True, identified[-1].get("activity", "")))
            results.append(
                _check(
                    "Event confidence >= 0.5",
                    float(identified[-1]["confidence"]) >= 0.5,
                    str(identified[-1]["confidence"]),
                )
            )
        except AssertionError as exc:
            results.append(_check("Latest activity event schema valid", False, str(exc)))
    else:
        results.append(
            _check(
                "Identified activity events in stream (optional without registered faces)",
                True,
                "No identified events yet — register faces from test video for identity pipeline proof",
            )
        )

    hb_active = status.get("status") == "active"
    if hb_active:
        results.append(_check("Worker status active", True, status.get("status", "")))
    else:
        results.append(_check("Worker status active", False, status.get("status", "unknown")))

    fps = status.get("fps")
    if fps:
        try:
            results.append(_check("Worker FPS reported", float(fps) >= 0.5, f"fps={fps}"))
        except ValueError:
            results.append(_check("Worker FPS reported", False, f"fps={fps}"))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 2 E2E acceptance criteria")
    parser.add_argument("--check-only", action="store_true", help="Prerequisites only")
    parser.add_argument("--full", action="store_true", help="Prerequisites + runtime Redis checks")
    parser.add_argument("--start-stream", action="store_true", help="Start simulate_streams.py in background")
    parser.add_argument("--video", default="", help="Override test video path")
    parser.add_argument("--camera-id", default=os.environ.get("TEST_CAMERA_ID", "CAM-01"))
    parser.add_argument("--rtmp-camera-id", default=os.environ.get("TEST_RTMP_CAMERA_ID", "cam01"))
    parser.add_argument("--host", default=os.environ.get("MEDIAMTX_HOST", "127.0.0.1"))
    parser.add_argument("--wait-seconds", type=float, default=90.0)
    args = parser.parse_args()

    if args.video:
        os.environ["TEST_VIDEO_PATH"] = args.video

    if not args.check_only and not args.full:
        args.check_only = True

    all_results = check_prerequisites()
    stream_proc = None

    try:
        if args.full and args.start_stream:
            if not test_video_path().exists():
                print(f"Test video missing: {test_video_path()}", file=sys.stderr)
                return 1
            stream_proc = start_rtmp_simulator(test_video_path(), camera_id=args.rtmp_camera_id, host=args.host)
            stream_proc.start()
            print(f"Started RTMP stream -> rtmp://{args.host}:1935/{args.rtmp_camera_id}")
            time.sleep(5)

        if args.full:
            print(f"Waiting up to {args.wait_seconds}s for worker outputs...")
            wait_for(
                lambda: redis_sync.get_camera_frame(args.camera_id) is not None,
                timeout_seconds=args.wait_seconds,
                description="camera_frame",
            )
            all_results.extend(check_runtime(camera_id=args.camera_id, timeout=args.wait_seconds))
    finally:
        if stream_proc is not None:
            stream_proc.stop()

    passed = sum(1 for r in all_results if r.passed)
    total = len(all_results)
    print("\nPhase 2 E2E verification")
    print("=" * 40)
    for result in all_results:
        mark = "PASS" if result.passed else "FAIL"
        line = f"[{mark}] {result.name}"
        if result.detail:
            line += f" — {result.detail}"
        print(line)
    print("=" * 40)
    print(f"{passed}/{total} checks passed")

    if args.full and passed == total:
        print("\nManual checks still recommended:")
        print("- DetectionsSmoother visual stability on decoded camera_frame")
        print("- Activity box colors (coding=green, collaborating=blue, mentoring=orange)")
        print("- RTSP interrupt: heartbeat status reconnecting -> active")
        print("- nvidia-smi VRAM with 2 workers (<4GB dev target)")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
