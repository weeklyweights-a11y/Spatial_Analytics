#!/usr/bin/env bash
# Phase 3 VM orchestration: sync venue, compose, streams, seed, verify.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"

echo "=== Phase 3 VM completion script ==="

python3 scripts/sync_venue_config.py 2>/dev/null || docker compose exec -T api python scripts/sync_venue_config.py

docker compose exec -T api alembic -c backend/db/migrations/alembic.ini upgrade head || docker compose run --rm api alembic -c backend/db/migrations/alembic.ini upgrade head

docker compose up -d --build scoring-engine

bash scripts/complete_phase2_vm.sh || true

python3 scripts/seed_phase3_test_participants.py || echo "WARN: participant seed failed"

echo "Waiting 120s for scoring flushes..."
sleep 120

docker compose exec -T api python scripts/verify_phase3_e2e.py --full

echo "PHASE_3_E2E_COMPLETE — run manual CCTV wall checks per docs/PHASE_3_E2E_CHECKLIST.md"
