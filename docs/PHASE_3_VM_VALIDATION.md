# Phase 3 VM Validation Notes

Run on `spatialscore-vm` after merging Phase 3:

1. `python scripts/sync_venue_config.py`
2. `docker compose exec api alembic upgrade head`
3. `docker compose up -d --build`
4. Start simulated streams (see `scripts/complete_phase2_vm.sh`)
5. `python scripts/seed_phase3_test_participants.py`
6. Wait 120s for scoring cycles
7. `docker compose exec api python scripts/verify_phase3_e2e.py --full`
8. Browser: admin login, CCTV wall, click bbox, profile link
9. Viewer login: leaderboard only, no CCTV
10. Soak 30 min; watch `/api/v1/health` scoring_engine + memory

Or run: `bash scripts/complete_phase3_vm.sh`
