# SpatialScore

Real-time spatial analytics for multi-camera venues. SpatialScore ingests CCTV streams, identifies people by face, tracks them across cameras, classifies activity from body pose and zone occupancy, and surfaces live scores, heatmaps, sponsor engagement, and exportable datasets for organizers.

## What it does

- **Identity:** SCRFD face detection + ArcFace embeddings + FAISS matching at registration; re-identification on every camera stream
- **Perception:** DEIMv2 whole-body (49 keypoints) person detection, ByteTrack tracking, polygon zone assignment
- **Activity:** Zone type + pose heuristics classify coding, collaborating, mentoring, presenting, networking, and more
- **Scoring:** Weighted minute accumulation with behavioral tags; live leaderboard and participant profiles
- **Operations:** CCTV monitoring wall (annotated MJPEG), heatmap, analytics, alerts, zone editor
- **Sponsors:** LineZone entry/exit counting, booth dwell reports, PDF exports
- **Export:** Admin CSV/TSV for scores, activity logs, and OpenTraj-compatible trajectories

## Architecture

![SpatialScore system architecture](docs/assets/spatialscore-architecture.png)

Single-VM deployment: PostgreSQL, Redis, API, workers, and dashboard orchestrated with Docker Compose. ONNX Runtime (CUDA) for all inference — no PyTorch at runtime.

**Data flow:** venue cameras relay through MediaMTX; each camera worker runs DEIMv2 detection, ByteTrack tracking, zone classification, and periodic face re-ID. Activity and sponsor crossing events land in Redis Streams. The scoring worker flushes to PostgreSQL and updates live Redis state; the heatmap worker publishes occupancy snapshots. The FastAPI layer serves REST, WebSockets, MJPEG streams, sponsor PDFs, and admin exports to the React dashboard.

## Tech stack

| Layer | Choices |
|-------|---------|
| CV | DEIMv2-wholebody49, InsightFace SCRFD/ArcFace, supervision (ByteTrack, PolygonZone, LineZone) |
| API | FastAPI, async SQLAlchemy, JWT auth |
| Data | PostgreSQL 16, Redis 7 (streams, leaderboard, live state) |
| UI | React 18, TypeScript, Vite, Tailwind, Recharts |
| PDF | WeasyPrint, Jinja2, matplotlib |

## Quick start

```bash
cp .env.example .env
# Set DB_PASSWORD and JWT_SECRET (32+ characters)

./scripts/download_models.sh   # ONNX weights into models/
docker compose up -d --build
docker compose exec api python -m backend.cli create-user --username admin --password YOURPASS --role admin
python scripts/sync_venue_config.py
```

| Service | URL |
|---------|-----|
| API health | http://localhost:8000/api/v1/health |
| Dashboard | http://localhost:3000 |

Default roles: **admin** (full access), **operator** (monitoring + reports), **viewer** (leaderboard/heatmap only).

## Configuration

- `configs/cameras.yaml` — RTSP URLs and floor assignment
- `configs/zones.yaml` — polygon zones and sponsor entrance lines
- `configs/sponsors.yaml` — sponsor booths and tiers
- `configs/scoring.yaml` — activity weights (also editable in Settings UI)

Venue config sync: `python scripts/sync_venue_config.py`

## Development

```bash
pip install -r backend/requirements.txt
export JWT_SECRET=test-jwt-secret-key-minimum-32-characters-long
pytest backend/tests/

cd dashboard && npm install && npm run build
```

GPU workers need NVIDIA Container Toolkit. CPU-only overlay: `docker-compose.cpu.yml`.

Set `WORKER_DATABASE_URL=postgresql://spatialscore:PASSWORD@postgres:5432/spatialscore` for camera worker name lookup.

## Verification

```bash
# Phase 5 smoke (API running, admin JWT):
python scripts/verify_phase5_e2e.py --token <JWT> --base-url http://localhost:8000
```

## License

MIT — see [LICENSE](LICENSE).
