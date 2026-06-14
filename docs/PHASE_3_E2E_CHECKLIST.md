# Phase 3 E2E Checklist

## Prerequisites

- [ ] Phase 2 pipeline passing (`scripts/verify_phase2_e2e.py --full`)
- [ ] `python scripts/sync_venue_config.py` — zones and cameras rows in Postgres
- [ ] Alembic migration `002_dev_activity_partitions` applied
- [ ] `python scripts/seed_phase3_test_participants.py` — 5+ faces registered
- [ ] Simulated streams running (2+ cameras)
- [ ] `redis-cli XLEN activity_stream` grows after registration

## Scoring engine

- [ ] `docker compose ps scoring-engine` — running
- [ ] After 2+ flush cycles (~120s): `scores.total_score > 0` for seeded participants
- [ ] `redis-cli ZREVRANGE leaderboard 0 9 WITHSCORES` — ranked entries
- [ ] `SELECT count(*) FROM activity_logs` — rows increasing
- [ ] Stop scoring worker, restart — no duplicate score inflation (idempotency)
- [ ] `/api/v1/health` — `scoring_engine` check fresh

## API

- [ ] `GET /api/v1/scores/leaderboard` — paginated, viewer allowed
- [ ] `GET /api/v1/scores/{id}` — admin/operator only; viewer gets 403
- [ ] `GET /api/v1/stream/CAM-01` — MJPEG with cookie auth
- [ ] Camera offline placeholder when worker stopped

## WebSocket

- [ ] `/ws/leaderboard?token=` — message within 35s
- [ ] `/ws/tracking/CAM-01` — tracking within 2s (admin/operator)
- [ ] Viewer rejected on `/ws/tracking/CAM-01`
- [ ] No JWT — close code 4001

## Dashboard (admin/operator)

- [ ] CCTV wall grid by floor
- [ ] MJPEG live feeds with labeled boxes
- [ ] Click bbox — score card (Escape / click-outside close)
- [ ] View Full Profile — `/participant/:id`
- [ ] Connection status bar on reconnect

## Dashboard (viewer)

- [ ] Login redirects to `/leaderboard`
- [ ] CCTV wall redirects to `/leaderboard`
- [ ] Leaderboard WS works; no MJPEG access

## Automated

- [ ] `python scripts/verify_phase3_e2e.py --full`

## Soak (VM)

- [ ] 30 min, 2 cameras, 5 participants — no memory growth; scoring lag OK in `/health`
