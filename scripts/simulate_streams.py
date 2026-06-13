#!/usr/bin/env python3
"""Push pre-recorded video as RTMP streams to MediaMTX for Phase 2 testing.

RTMP path uses lowercase camera id (cam01). Compose workers use CAM-01 with
RTSP rtsp://mediamtx:8554/cam01.

Examples:
  python scripts/simulate_streams.py --video test_data/test.mp4 --camera-id cam01
  python scripts/simulate_streams.py --video test_data/a.mp4 --camera-id cam01 &
  python scripts/simulate_streams.py --video test_data/b.mp4 --camera-id cam02 &
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate RTMP camera streams via ffmpeg")
    parser.add_argument("--video", required=True, help="Path to MP4 video file")
    parser.add_argument(
        "--camera-id",
        required=True,
        help="Lowercase RTMP path segment (e.g. cam01, cam02)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="MediaMTX host (use mediamtx when running inside compose network)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=5,
        help="Output frame rate for simulated CCTV feed (default: 5)",
    )
    parser.add_argument("--loop", action="store_true", default=True, help="Loop video (default: on)")
    args = parser.parse_args()

    video = Path(args.video)
    if not video.exists():
        print(f"Video not found: {video}", file=sys.stderr)
        sys.exit(1)

    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found on PATH", file=sys.stderr)
        sys.exit(1)

    cam = args.camera_id.lower()
    rtmp_url = f"rtmp://{args.host}:1935/{cam}"
    cmd = [
        "ffmpeg",
        "-re",
    ]
    if args.loop:
        cmd.extend(["-stream_loop", "-1"])
    cmd.extend(
        [
            "-i",
            str(video),
            "-r",
            str(args.fps),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-f",
            "flv",
            rtmp_url,
        ]
    )
    print(f"Streaming {video} -> {rtmp_url} at {args.fps} FPS")
    proc = subprocess.Popen(cmd)
    proc.wait()


if __name__ == "__main__":
    main()
