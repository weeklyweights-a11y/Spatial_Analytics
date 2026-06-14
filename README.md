# SpatialScore

Real-time hackathon intelligence platform — Phase 3: scoring engine + CCTV wall MVP.

## Phase 3 dashboard

- **CCTV wall:** `/cctv-wall` (admin/operator) — MJPEG grid, click-to-inspect score cards
- **Viewer role:** `/leaderboard` and `/heatmap` only; no PII score detail or camera streams
- **Same-origin:** dashboard nginx proxies `/api/v1/stream/` and `/ws/` with cookies for MJPEG auth
- **Verify:** `python scripts/verify_phase3_e2e.py --full` after compose + scoring worker up

## Prerequisites

- **GCP project:** `buildathon-499300` (number `635695586626`), account `bhargavin189@gmail.com`
- GCE **g2-standard-8** VM with **NVIDIA L4**, Ubuntu 24.04
- Docker + NVIDIA Container Toolkit
- SSH access
- Optional domain: `https://spatialscore.buildathon.co`

```bash
gcloud config set account bhargavin189@gmail.com
gcloud config set project buildathon-499300
```

## Deployed VM (buildathon-499300)

| Field | Value |
|-------|-------|
| Instance | `spatialscore-vm` |
| Zone | `asia-east1-a` |
| Type | `e2-standard-8` (interim CPU — upgrade to `g2-standard-8` + L4 when GPU quota approved) |
| External IP | set via `gcloud compute instances describe spatialscore-vm --format='get(networkInterfaces[0].accessConfigs[0].natIP)'` |

```bash
gcloud config set account bhargavin189@gmail.com
gcloud config set project buildathon-499300
gcloud compute ssh spatialscore-vm --zone=asia-east1-a
cd ~/spatialscore && sudo docker compose ps
```

**GPU quota:** Project global `GPUS_ALL_REGIONS` is currently 0 — request L4 quota in [GCP Console Quotas](https://console.cloud.google.com/iam-admin/quotas?project=buildathon-499300) before switching to `g2-standard-8`.

## Quick start (GCP VM)

```bash
git clone <repo-url> spatialscore && cd spatialscore
chmod +x scripts/*.sh
./scripts/setup_gcp.sh
```

Or manually:

```bash
cp .env.example .env   # set DB_PASSWORD, JWT_SECRET (32+ chars)
./scripts/download_models.sh
docker compose up -d --build
docker compose exec api python -m backend.cli create-user --username admin --password YOURPASS --role admin
```

- API: http://localhost:8000/api/v1/health
- Dashboard: http://localhost:3000

## Design notes

- **Uvicorn 1 worker** in Phase 1 (FAISS in-process; multi-worker would stale indexes across registration tablets)
- **Registration staff workflow:** verify participant **physical ID** before face capture ([prd.md](prd.md))
- **Venue signage** and post-event anonymize: Phase 6 ops

## Docs

- [docs/PHASE_1_SPEC.md](docs/PHASE_1_SPEC.md)
- [docs/PHASE_2_SPEC.md](docs/PHASE_2_SPEC.md)
- [docs/PHASE_2_E2E_CHECKLIST.md](docs/PHASE_2_E2E_CHECKLIST.md)
- [docs/REFERENCE_REPOS.md](docs/REFERENCE_REPOS.md)
- [models/README.md](models/README.md)
- [docs/BROWSER_E2E_CHECKLIST.md](docs/BROWSER_E2E_CHECKLIST.md)

## Development

```bash
pip install -r backend/requirements.txt
export JWT_SECRET=test-jwt-secret-key-minimum-32-characters-long
pytest backend/tests/
cd dashboard && npm install && npm test
```

## Phase 2 testing (camera pipeline)

```bash
# CPU-only VM (no GPU quota):
docker compose up -d --build

# GPU production VM:
# docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build

# Push test RTMP (host mediamtx when on VM):
python scripts/simulate_streams.py --video test_data/test.mp4 --camera-id cam01 --host mediamtx

# Inspect Redis events:
redis-cli XREAD COUNT 5 STREAMS activity_stream 0
redis-cli HGETALL zone_occupancy
redis-cli HGETALL camera_status:CAM-01

# Automated E2E verification (on VM):
python scripts/verify_phase2_e2e.py --check-only
python scripts/verify_phase2_e2e.py --full --start-stream --video test_data/test.mp4

# Integration test suite (requires models, test video, ffmpeg, Redis, MediaMTX):
export RUN_INTEGRATION_TESTS=1 DEIMv2_INTEGRATION=1
pytest backend/tests/integration/test_camera_pipeline.py backend/tests/integration/test_identity_pipeline.py -v -m integration
```

Set `WORKER_DATABASE_URL=postgresql://spatialscore:PASSWORD@postgres:5432/spatialscore` for camera worker name lookup.

## Phase 1 scope

Docker Compose (MediaMTX, PostgreSQL, Redis, API, dashboard), JWT auth, SCRFD/ArcFace/FAISS registration, React registration UI. Phase 2 adds camera workers, DEIMv2 pipeline, and Redis activity events.
