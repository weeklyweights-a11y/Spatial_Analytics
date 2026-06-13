# SpatialScore

Real-time hackathon intelligence platform — Phase 1: infrastructure + face registration.

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

## Phase 1 scope

Docker Compose (MediaMTX, PostgreSQL, Redis, API, dashboard), JWT auth, SCRFD/ArcFace/FAISS registration, React registration UI. Camera workers and scoring are placeholders.
