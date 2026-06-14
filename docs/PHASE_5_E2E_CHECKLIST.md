# Phase 5 E2E Checklist

## Sponsor tracking

- [ ] `sponsor_lines` in `configs/zones.yaml` for 2+ booths (CAM-01, CAM-02)
- [ ] LineZone entry/exit events in Redis `sponsor_stream`
- [ ] `participant_sponsor_visits` rows with entry/exit and dwell
- [ ] Auto-close after 30 min without booth-zone activity
- [ ] `sponsor_engagement` hourly aggregates updated

## Sponsor reports

- [ ] `GET /api/v1/sponsors` list
- [ ] `GET /api/v1/sponsors/{id}/report` — all 8 metrics, hourly traffic (visitors + entries), by_track with `other`, by_floor
- [ ] `GET /api/v1/sponsors/{id}/report/pdf` — valid PDF download
- [ ] Sponsor Reports dashboard page with comparison chart
- [ ] Download PDF button (admin only)

## Participant profile

- [ ] Timeline with expandable sub-activity breakdown
- [ ] Sponsor visits narrative section
- [ ] Zones and floors section
- [ ] `GET /participants/{id}/sponsor-visits`
- [ ] `GET /participants/{id}/zone-history`

## Data export

- [ ] `GET /export/scores` CSV
- [ ] `GET /export/activity-logs` streaming
- [ ] `GET /export/trajectories?format=opentraj`
- [ ] `?anonymize=true` on trajectories
- [ ] Operator and viewer get 403 on exports
- [ ] Settings Export tab with progress bar
- [ ] Leaderboard Export Scores button (admin)

## Infrastructure

- [ ] Migration 004 applied
- [ ] `python scripts/sync_venue_config.py`
- [ ] WeasyPrint deps in Docker image
- [ ] `pytest` Phase 5 unit + integration tests pass
- [ ] `python scripts/verify_phase5_e2e.py --token <JWT>`

## Runbook

```bash
alembic upgrade head
python scripts/sync_venue_config.py
docker compose build api scoring-engine camera-worker-01 camera-worker-02 dashboard
docker compose up -d
pytest backend/tests/unit/test_sponsor_aggregation.py backend/tests/unit/test_trajectory_export.py backend/tests/unit/test_pdf_generation.py
pytest backend/tests/integration/test_sponsor_pipeline.py backend/tests/integration/test_exports.py backend/tests/integration/test_sponsor_pdf.py
python scripts/verify_phase5_e2e.py --token <JWT>
```
