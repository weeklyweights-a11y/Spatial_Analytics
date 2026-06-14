#!/usr/bin/env bash
# Phase 3 full E2E orchestration (local or VM).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"

echo "=== Phase 3 E2E completion ==="

docker compose exec -T api alembic -c backend/db/migrations/alembic.ini upgrade head
docker compose exec -T api python scripts/sync_venue_config.py

docker compose exec -T api python -m backend.cli reset-password \
  --username "$ADMIN_USERNAME" --password "$ADMIN_PASSWORD" 2>/dev/null \
  || docker compose exec -T api python -m backend.cli create-user \
  --username "$ADMIN_USERNAME" --password "$ADMIN_PASSWORD" --role admin

docker compose exec -T api python -m backend.cli create-user \
  --username testviewer --password testpass123 --role viewer 2>/dev/null || true

docker compose up -d --build api dashboard scoring-engine camera-worker-01 camera-worker-02 mediamtx

docker compose up -d --build api dashboard scoring-engine camera-worker-01 camera-worker-02 mediamtx

bash scripts/simulate_streams_docker.sh

sleep 30
docker compose restart camera-worker-01 camera-worker-02

export API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
python3 scripts/seed_phase3_test_participants.py

echo "Waiting 125s for identity linking + 2 scoring flushes..."
sleep 125

python3 scripts/verify_phase3_e2e.py --full

echo ""
echo "PHASE_3_E2E_COMPLETE"
echo "Manual: open http://localhost:3000 — admin login, CCTV wall, click bbox, viewer -> leaderboard only"
