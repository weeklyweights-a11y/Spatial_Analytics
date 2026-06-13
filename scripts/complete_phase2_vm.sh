#!/usr/bin/env bash
# Run on spatialscore-vm after docker compose is up. Validates Phase 2 with simulated streams.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export PYTHONPATH="$ROOT"

echo "=== Phase 2 VM completion script ==="

mkdir -p test_data data/faiss logs

HACKATHON_VIDEO="test_data/hackathon_workspace.mp4"
CAREER_FAIR_VIDEO="test_data/career_fair_meeting.mp4"

if [[ ! -f "$HACKATHON_VIDEO" ]]; then
  echo "Downloading hackathon-style team planning video (Mixkit)..."
  wget -q -O "$HACKATHON_VIDEO" "https://assets.mixkit.co/videos/13231/13231-720.mp4"
fi

if [[ ! -f "$CAREER_FAIR_VIDEO" ]]; then
  echo "Downloading career-fair-style office meeting video (Mixkit)..."
  wget -q -O "$CAREER_FAIR_VIDEO" "https://assets.mixkit.co/videos/46682/46682-720.mp4"
fi

SIM_VIDEO="$HACKATHON_VIDEO"
if [[ ! -f "$SIM_VIDEO" ]]; then
  SIM_VIDEO="$CAREER_FAIR_VIDEO"
fi

if [[ ! -f test_data/test.mp4 ]]; then
  cp "$SIM_VIDEO" test_data/test.mp4
fi

if [[ ! -f models/deimv2_s_wholebody49.onnx ]]; then
  echo "Downloading interim DEIMv2 ONNX (COCO det; replace with wholebody49 export on GPU VM)..."
  wget -q -O models/deimv2_s_wholebody49.onnx \
    "https://huggingface.co/carpedm20/DEIMv2/resolve/main/deimv2_dinov3_s_coco.onnx"
fi

echo "Building and starting stack..."
docker compose -f docker-compose.yml up -d --build --remove-orphans
docker compose restart mediamtx
sleep 5
echo "Waiting for health..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

pkill -f "simulate_streams.py" 2>/dev/null || true
pkill -f "ffmpeg.*rtmp://.*1935/cam" 2>/dev/null || true
sleep 2

echo "Starting simulated RTMP streams (cam01-03) at 5 FPS..."
for cam in cam01 cam02 cam03; do
  video="$SIM_VIDEO"
  if [[ "$cam" == "cam02" ]] && [[ -f "$CAREER_FAIR_VIDEO" ]]; then
    video="$CAREER_FAIR_VIDEO"
  fi
  nohup python3 scripts/simulate_streams.py --video "$video" --camera-id "$cam" --host 127.0.0.1 --fps 5 \
    > "/tmp/sim_${cam}.log" 2>&1 &
done
sleep 30

echo "--- Worker logs (CAM-01) ---"
docker compose logs camera-worker-01 --tail 5

echo "--- Redis camera_status:CAM-01 ---"
redis-cli HGETALL camera_status:CAM-01 || true
FRAME_TTL=$(redis-cli TTL camera_frame:CAM-01 || echo -2)
echo "camera_frame:CAM-01 TTL=$FRAME_TTL"

echo "--- Register participant from test video (optional) ---"
docker compose exec -T api python << 'PY'
import os
import sys
import uuid

import cv2
import httpx

video = "/app/test_data/test.mp4"
if not os.path.exists(video):
    print("SKIP: test video not mounted in api container")
    sys.exit(0)

cap = cv2.VideoCapture(video)
ok, frame = cap.read()
cap.release()
if not ok:
    print("SKIP: cannot read video frame")
    sys.exit(0)

_, buf = cv2.imencode(".jpg", frame)
jpeg = buf.tobytes()

password = os.environ.get("ADMIN_PASSWORD", "admin")
with httpx.Client(base_url="http://127.0.0.1:8000", timeout=60) as client:
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": password})
    if login.status_code != 200:
        print(f"SKIP registration: login {login.status_code}")
        sys.exit(0)
    token = login.json()["data"]["token"]
    reg = client.post(
        "/api/v1/register",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "name": f"Phase2 E2E {uuid.uuid4().hex[:6]}",
            "team_name": "E2E Team",
            "track": "ai_ml",
            "consent_confirmed": "true",
        },
        files={"photo": ("frame.jpg", jpeg, "image/jpeg")},
    )
    print(f"registration status={reg.status_code} body={reg.text[:200]}")
PY

echo "Waiting 45s for identity linking..."
sleep 45

echo "--- activity_stream ---"
redis-cli XLEN activity_stream
redis-cli XREAD COUNT 2 STREAMS activity_stream 0 2>/dev/null || true

echo "--- E2E verify ---"
docker compose exec -T api python scripts/verify_phase2_e2e.py --full
VERIFY_EXIT=$?

echo "--- Health ---"
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool | head -40

if [[ "$VERIFY_EXIT" -eq 0 ]] && [[ "$FRAME_TTL" -gt 0 ]]; then
  echo "PHASE_2_E2E_PASS"
  exit 0
fi

echo "PHASE_2_E2E_FAIL — see logs above"
exit 1
