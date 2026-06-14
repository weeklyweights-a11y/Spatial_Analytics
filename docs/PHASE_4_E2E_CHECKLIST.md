# Phase 4 E2E Checklist

Last verified: 2026-06-14 (local Docker stack)

## Prerequisites

- [x] Phase 3 stack running (`docker compose up`)
- [x] Run `python scripts/sync_venue_config.py` after migration 003
- [ ] 2+ simulated camera streams and 5+ registered participants (optional for full alert validation)

## Heatmap

- [x] Heatmap worker inserts rows every ~10s (`SELECT count(*) FROM heatmap_snapshots` — 19+ rows)
- [x] `GET /api/v1/analytics/heatmap` returns zones with count/pct
- [x] Heatmap page loads with Zones sidebar and Energy Level (`/heatmap`)
- [ ] Zone sidebar bidirectional highlight (manual visual check)

## Analytics

- [x] `GET /api/v1/analytics/energy` with defaults (24h, interval 30)
- [x] Analytics page energy graph and zone utilization panels (`/analytics`)

## Alerts

- [x] Capacity >90% fires alert (Alert Test Zone at 95% in DB + CCTV AlertsFeed)
- [x] CCTV AlertsFeed shows alerts with Acknowledge buttons (`/cctv-wall`)
- [x] `GET/PUT /api/v1/alerts` (list + acknowledge tested)

## Leaderboard

- [x] Sort/filter/compare controls on Leaderboard page (`/leaderboard`)
- [ ] `GET /api/v1/scores/compare?ids=` (no registered participants in DB to compare)

## Settings

- [x] Settings page zone editor + scoring weights tabs (`/settings`)
- [x] Zone CRUD via API (POST/PUT/DELETE fresh zone)
- [x] Scoring weights GET/PUT + worker reload (integration test pattern verified via API PUT)

## Automated

```bash
pytest backend/tests/unit/test_alert_engine.py backend/tests/unit/test_heatmap_worker.py
python scripts/verify_phase4_e2e.py --token <JWT>
python scripts/run_phase4_e2e_extended.py --token <JWT>
```

Results (2026-06-14):

- Unit tests: 8/8 passed
- `verify_phase4_e2e.py`: 5/5 passed
- `run_phase4_e2e_extended.py`: 10/10 passed
- Migration: `003_phase4_alerts_floor_polygon` applied
- Health: `heatmap_worker` check present and OK
