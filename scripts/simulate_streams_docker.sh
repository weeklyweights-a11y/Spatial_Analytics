#!/usr/bin/env bash
# Push simulated RTMP streams via Docker ffmpeg (no host ffmpeg required).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

NETWORK="${COMPOSE_NETWORK:-buildathon_cctv_default}"
HOST="${MEDIAMTX_HOST:-mediamtx}"
VIDEO1="${1:-test_data/hackathon_workspace.mp4}"
VIDEO2="${2:-test_data/career_fair_meeting.mp4}"
FPS="${SIM_FPS:-5}"

stop_streams() {
  docker rm -f spatialscore-sim-cam01 spatialscore-sim-cam02 2>/dev/null || true
}

start_stream() {
  local name="$1"
  local video="$2"
  local cam="$3"
  docker run -d --name "$name" --network "$NETWORK" \
    -v "$ROOT/$video:/video.mp4:ro" \
    jrottenberg/ffmpeg:4.4-alpine \
    -re -stream_loop -1 -i /video.mp4 -r "$FPS" -c:v libx264 -preset veryfast -f flv "rtmp://${HOST}:1935/${cam}"
}

stop_streams
start_stream spatialscore-sim-cam01 "$VIDEO1" cam01
start_stream spatialscore-sim-cam02 "$VIDEO2" cam02
echo "Started Docker ffmpeg simulators on network $NETWORK"
