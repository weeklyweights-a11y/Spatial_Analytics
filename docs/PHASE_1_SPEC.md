# Phase 1: Infrastructure + Registration

## What This Phase Does

Set up the entire foundation: GCP VM configuration, Docker Compose with all services, database schema, auth system, logging framework, health checks, and the face registration pipeline. By the end of this phase, you can start Docker Compose on the GCP VM, open the registration UI on a tablet, register participants by capturing their face, and see their profile stored in PostgreSQL with their face embedding in FAISS. The scoring engine, camera workers, and CCTV wall are NOT built yet — but every infrastructure pattern they need (database connections, Redis clients, auth middleware, logging, error handling, config management) is established and tested.

This phase is boring on purpose. It's plumbing. But if the plumbing is wrong, every subsequent phase fights it.

## Prerequisites

- GCE g2-standard-8 VM provisioned with NVIDIA L4 GPU, Ubuntu 24.04, Docker + NVIDIA Container Toolkit installed
- SSH access to the VM
- Domain pointed at VM IP (optional, can use raw IP for now)

---

## Resources to Download + Install

Everything below is downloaded to the GCP VM during setup. Nothing goes on the venue laptop.

### Model Weights (downloaded once, stored in models/ directory on VM)

**InsightFace buffalo_l model pack** — contains both SCRFD and ArcFace:
```bash
# Option A: via pip (auto-downloads to ~/.insightface/models/buffalo_l/)
pip install insightface
python -c "
from insightface.app import FaceAnalysis
app = FaceAnalysis('buffalo_l', providers=['CPUExecutionProvider'])
app.prepare(ctx_id=-1)
"
cp ~/.insightface/models/buffalo_l/det_10g.onnx models/scrfd_10g.onnx       # 16 MB, face detection
cp ~/.insightface/models/buffalo_l/w600k_r50.onnx models/arcface_r100.onnx  # 166 MB, face recognition

# Option B: direct download from HuggingFace
wget https://huggingface.co/public-data/insightface/resolve/main/models/buffalo_l/det_10g.onnx -O models/scrfd_10g.onnx
wget https://huggingface.co/public-data/insightface/resolve/main/models/buffalo_l/w600k_r50.onnx -O models/arcface_r100.onnx
```

**DEIMv2 wholebody49** — not used in Phase 1 but downloaded now so it's ready for Phase 2:
```bash
# Clone the DEIMv2 repo, export the pose model to ONNX
git clone https://github.com/Intellindust-AI-Lab/DEIMv2.git /tmp/deimv2
cd /tmp/deimv2
# Follow their export instructions to create ONNX file
# Exact command depends on their repo structure — check their README
# Result: models/deimv2_s_wholebody49.onnx (~40 MB)
```

### Python Libraries (installed in Docker image via requirements.txt)

```
# backend/requirements.txt — Phase 1 dependencies

# Web framework
fastapi>=0.110
uvicorn[standard]>=0.27
python-multipart>=0.0.6

# Database
sqlalchemy[asyncio]>=2.0
asyncpg>=0.29
alembic>=1.13
psycopg2-binary>=2.9

# Redis
redis>=5.0

# Auth
python-jose[cryptography]>=3.3
passlib[bcrypt]>=1.7

# ML / CV (used in registration face pipeline)
onnxruntime-gpu>=1.17        # runs SCRFD + ArcFace on GPU
opencv-python>=4.9            # image decoding, preprocessing
numpy>=1.24                   # array operations
faiss-cpu>=1.7                # face embedding similarity search
insightface>=0.7.3            # model download helper (not used at runtime)

# Validation
pydantic>=2.5
pydantic-settings>=2.1

# Logging
loguru>=0.7

# Rate limiting
slowapi>=0.1.9

# Data
pandas>=2.1

# Utils
pyyaml>=6.0
```

### npm Packages (installed in Docker image via package.json)

```json
{
  "dependencies": {
    "react": "^18.3",
    "react-dom": "^18.3",
    "react-router-dom": "^6.22",
    "@tanstack/react-query": "^5.28",
    "zustand": "^4.5",
    "recharts": "^2.12",
    "lucide-react": "^0.344",
    "axios": "^1.6"
  },
  "devDependencies": {
    "typescript": "^5.4",
    "vite": "^5.2",
    "@vitejs/plugin-react": "^4.2",
    "tailwindcss": "^3.4",
    "autoprefixer": "^10.4",
    "postcss": "^8.4",
    "@types/react": "^18.2",
    "@types/react-dom": "^18.2"
  }
}
```

Note: `reconnecting-websocket`, `d3`, and `react-pdf/renderer` are NOT installed in Phase 1. They're added in Phase 3 and Phase 5 when needed.

### Code Patterns Extracted from Open Source Repos

We do NOT clone or fork these repos. We study their approach and rewrite the relevant logic in our own code. Here's exactly what we take from each:

**From [vectornguyen76/face-recognition](https://github.com/vectornguyen76/face-recognition):**
- `face_detection/` → study how they wrap SCRFD ONNX: input preprocessing (resize, normalize, transpose), session.run() call, output parsing (boxes, scores, landmarks). Rewrite as our `backend/core/face_detector.py`.
- `face_alignment/` → study their 5-point landmark → affine transform → 112x112 aligned crop. Rewrite as a function in our `backend/core/face_recognizer.py`.
- `face_recognition/arcface/` → study their ArcFace ONNX wrapper: input preprocessing (aligned face → float32 → normalize), session.run(), output L2-normalization. Rewrite as our `backend/core/face_recognizer.py`.

**From [yakhyo/face-reidentification](https://github.com/yakhyo/face-reidentification):**
- `database/` → study their FAISS IndexFlatIP setup: index creation, add(), search() with cosine similarity, save_index(), load_index(). Rewrite as our `backend/core/face_matcher.py`. Key pattern: L2-normalize embeddings before adding to IndexFlatIP, so inner product = cosine similarity.

**From [zerokhong1/face-recognition-system](https://github.com/zerokhong1/face-recognition-system):**
- `backend/main.py` → study their FastAPI app structure: lifespan events for model loading, router organization, middleware setup. Use as reference for our `backend/main.py`.
- `backend/feature_matcher.py` → study their FAISS wrapper with batch query pattern. Reference for our face_matcher.py.

**How to study these repos:** Clone them locally, read the relevant files, understand the approach, then write our own version. Do not copy-paste. Our code will be structured differently (async, Pydantic v2 models, loguru logging, different file organization). The repos are reference implementations, not source code to fork.

### Docker Images (pulled automatically by Docker Compose)

```
postgres:16-alpine          — PostgreSQL database
redis:7-alpine              — Redis cache + message stream
bluenviron/mediamtx:latest  — RTMP/RTSP media relay server
```

## Section 0: Resource Acquisition

Before writing any code, download and set up all the resources this phase depends on. This section tells you exactly what to get, where to get it, and what to extract from each.

### 0.1 Model Downloads

**InsightFace buffalo_l model pack (SCRFD + ArcFace):**
```bash
pip install insightface
python -c "
from insightface.app import FaceAnalysis
app = FaceAnalysis('buffalo_l', providers=['CPUExecutionProvider'])
app.prepare(ctx_id=-1)
"
# Models downloaded to ~/.insightface/models/buffalo_l/
cp ~/.insightface/models/buffalo_l/det_10g.onnx models/scrfd_10g.onnx
cp ~/.insightface/models/buffalo_l/w600k_r50.onnx models/arcface_r100.onnx
```
- `scrfd_10g.onnx` (16 MB) — face detection model. Used in `backend/core/face_detector.py`
- `arcface_r100.onnx` (166 MB) — face embedding model. Used in `backend/core/face_recognizer.py`

**DEIMv2-wholebody49 (download now, used in Phase 2):**
```bash
git clone https://github.com/Intellindust-AI-Lab/DEIMv2.git /tmp/deimv2
# Check available configs for wholebody/pose variants
# Export to ONNX:
# cd /tmp/deimv2 && python tools/export_onnx.py --config configs/deimv2_s_wholebody49.yml --output models/deimv2_s_wholebody49.onnx
```
- If the exact wholebody49 config doesn't exist, download the closest pose estimation variant and document the actual keypoint count
- Place the ONNX file in `models/deimv2_s_wholebody49.onnx`
- This model is NOT used in Phase 1 but should be downloaded now so Phase 2 doesn't block on it

### 0.2 Code to Extract from Open Source Repos

**[vectornguyen76/face-recognition](https://github.com/vectornguyen76/face-recognition) — SCRFD + ArcFace pipeline:**
```bash
git clone https://github.com/vectornguyen76/face-recognition.git /tmp/face-recognition
```
Extract and adapt into our codebase:
- `/tmp/face-recognition/face_detection/` → adapt SCRFD ONNX wrapper (preprocessing, inference, postprocessing) into `backend/core/face_detector.py`. Take: the input preprocessing (resize, normalize, pad), the ONNX session setup with provider selection, the output parsing (bounding boxes, landmarks, confidence). Don't take: their CLI/demo code, their video processing loop.
- `/tmp/face-recognition/face_alignment/` → adapt the 5-point landmark alignment (affine transform to 112x112) into `backend/core/face_recognizer.py` as a preprocessing step before ArcFace. Take: the alignment matrix calculation using the 5 SCRFD landmarks, the cv2.warpAffine call. Don't take: their batch processing code.
- `/tmp/face-recognition/face_recognition/arcface/` → adapt ArcFace ONNX inference into `backend/core/face_recognizer.py`. Take: the ONNX session setup, the input preprocessing (112x112 BGR, normalize), the output L2 normalization. Don't take: their model training code.

**[yakhyo/face-reidentification](https://github.com/yakhyo/face-reidentification) — FAISS implementation:**
```bash
git clone https://github.com/yakhyo/face-reidentification.git /tmp/face-reid
```
Extract into our codebase:
- `/tmp/face-reid/` → adapt the FAISS IndexFlatIP setup and search pattern into `backend/core/face_matcher.py`. Take: the index creation (`faiss.IndexFlatIP(512)`), the `index.add()` with L2-normalized vectors, the `index.search()` batch query pattern, the `faiss.write_index()` / `faiss.read_index()` persistence. Don't take: their main.py, their SCRFD/ArcFace wrappers (we use vectornguyen76's versions).

**[zerokhong1/face-recognition-system](https://github.com/zerokhong1/face-recognition-system) — FastAPI + React architecture:**
```bash
git clone https://github.com/zerokhong1/face-recognition-system.git /tmp/face-system
```
Extract and adapt into our codebase:
- `/tmp/face-system/backend/main.py` → reference for FastAPI app structure with CORS, middleware, router mounting. Adapt patterns into `backend/main.py`. Take: the app factory pattern, the lifespan handler for startup/shutdown, the router organization. Don't take: their specific endpoints or CV pipeline.
- `/tmp/face-system/backend/feature_matcher.py` → reference for FAISS wrapper patterns (already covered by yakhyo above, use as secondary reference)
- `/tmp/face-system/dashboard/src/` → reference for React component structure. Take: the folder organization pattern (pages/, components/, hooks/). Don't take: their specific components (we build our own CCTV wall).

### 0.3 Python Dependencies

Create `backend/requirements.txt`:
```
# Core CV
onnxruntime-gpu>=1.17.0
insightface>=0.7.3
opencv-python>=4.9.0
numpy>=1.24.0
faiss-cpu>=1.7.0
scikit-learn>=1.3.0
supervision>=0.28.0

# Backend
fastapi>=0.110.0
uvicorn>=0.27.0
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
alembic>=1.13.0
redis>=5.0.0
pydantic>=2.5.0
python-multipart>=0.0.6
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4

# Data + Export
pandas>=2.1.0

# Infrastructure
loguru>=0.7.0
slowapi>=0.1.9
pyyaml>=6.0.0

# Testing
pytest>=7.0.0
pytest-asyncio>=0.23.0
httpx>=0.25.0
```

### 0.4 Frontend Dependencies

Initialize the React project and install:
```bash
npm create vite@latest dashboard -- --template react-ts
cd dashboard
npm install tailwindcss @tailwindcss/vite
npm install react-router-dom@6
npm install @tanstack/react-query@5
npm install zustand
npm install reconnecting-websocket
npm install recharts
npm install lucide-react
npm install axios
```

### 0.5 Docker Images to Pull

```bash
docker pull bluenviron/mediamtx:latest
docker pull postgres:16-alpine
docker pull redis:7-alpine
```

### 0.6 Create Directory Structure

```bash
mkdir -p models data/faces data/faiss data/venue data/exports data/backups logs
mkdir -p configs scripts tests/unit tests/integration tests/e2e docs deploy
mkdir -p backend/api backend/core backend/workers backend/db backend/utils
```

### What to build

A `docker-compose.yml` at the project root that starts all services with a single `docker compose up`. For Phase 1, only the following services need to be functional: `postgres`, `redis`, `api`, `dashboard`, `mediamtx`. The camera worker and scoring engine containers should be defined but can start with a placeholder command that sleeps (they become real in Phase 2 and 3).

### Services

**mediamtx** — bluenviron/mediamtx:latest container. Exposes port 1935 (RTMP ingest from venue) and port 8554 (local RTSP re-stream). Mount a mediamtx.yml config that accepts RTMP push on any path and re-publishes as RTSP. No authentication on MediaMTX for now — security is handled at the GCP firewall level.

**postgres** — postgres:16-alpine container. Named volume for data persistence. Environment variables for database name, user, password from .env. Health check: `pg_isready`. Exposes port 5432 only on Docker internal network (not to host).

**redis** — redis:7-alpine container. AOF persistence enabled (`--appendonly yes`). Max memory 2GB with allkeys-lru eviction. Named volume for data persistence. Health check: `redis-cli ping`. Exposes port 6379 only on Docker internal network.

**api** — Custom Dockerfile built from backend/. FastAPI app on uvicorn with 4 workers. Depends on postgres and redis. Environment variables: DATABASE_URL, REDIS_URL, JWT_SECRET, FAISS_INDEX_PATH, MODELS_DIR. Exposes port 8000 to host. Resource limits: 4 CPUs, 4GB RAM.

**dashboard** — Custom Dockerfile built from dashboard/. React app served by nginx. Exposes port 3000 to host. Static build, no server-side rendering.

**camera-worker-placeholder** — Same backend image, command `python -c "import time; time.sleep(999999)"`. GPU access via nvidia runtime. This becomes real in Phase 2.

**scoring-engine-placeholder** — Same backend image, command `python -c "import time; time.sleep(999999)"`. This becomes real in Phase 3.

### Environment

Create `.env.example` with all required variables:
```
DB_PASSWORD=changeme
JWT_SECRET=changeme-generate-a-real-secret
GCS_BUCKET=spatialscore-data
FAISS_INDEX_PATH=/app/data/faiss/faiss_index.bin
MODELS_DIR=/app/models
LOG_LEVEL=INFO
```

Create `.env` from the example on the VM (gitignored).

### Volumes and mounts

Mount `./models` directory into api and worker containers at `/app/models` (read-only).
Mount `./data` directory into api container at `/app/data` (read-write, for FAISS index and registration photos).
Mount `./configs` directory into api and worker containers at `/app/configs` (read-only).

---

## Section 2: Database Schema + Migrations

### What to build

All database tables created via Alembic migration. Every table that any phase will use is created now — not just Phase 1 tables. This prevents migration headaches later. Tables can be empty; the schema just needs to exist.

### Tables to create

**participants** — id (UUID, PK, default gen_random_uuid()), name (VARCHAR 255, NOT NULL), email (VARCHAR 255, nullable), team_name (VARCHAR 255, NOT NULL), track (VARCHAR 100, NOT NULL), skills (TEXT array, nullable), photo_path (VARCHAR 500, nullable), embedding_id (INTEGER, nullable — position in FAISS index), registered_at (TIMESTAMP WITH TIME ZONE, default NOW()), opted_out (BOOLEAN, default FALSE).

**scores** — participant_id (UUID, PK, FK → participants), total_score (FLOAT, default 0), coding_minutes (FLOAT, default 0), collaborating_minutes (FLOAT, default 0), mentoring_minutes (FLOAT, default 0), presenting_minutes (FLOAT, default 0), networking_minutes (FLOAT, default 0), helping_minutes (FLOAT, default 0), idle_minutes (FLOAT, default 0), tags (TEXT array, default empty), rank (INTEGER, nullable), last_zone (VARCHAR 100, nullable), last_activity (VARCHAR 50, nullable), last_seen_at (TIMESTAMP, nullable), updated_at (TIMESTAMP, default NOW()).

**activity_logs** — id (BIGSERIAL, PK), participant_id (UUID, NOT NULL, FK → participants), camera_id (VARCHAR 50, NOT NULL), zone_id (UUID, NOT NULL, FK → zones), activity (VARCHAR 50, NOT NULL), bbox (JSONB, nullable), confidence (FLOAT, nullable), timestamp (TIMESTAMP, NOT NULL, default NOW()). Partitioned by RANGE on timestamp. Create 24 hourly partitions covering the event window. Index on (participant_id, timestamp) and (zone_id, timestamp).

**zones** — id (UUID, PK), name (VARCHAR 100, NOT NULL), zone_type (VARCHAR 50, NOT NULL), camera_id (VARCHAR 50, NOT NULL), polygon_coords (JSONB, NOT NULL), floor (INTEGER, NOT NULL), capacity (INTEGER, nullable), sponsor_id (UUID, nullable, FK → sponsors), created_at (TIMESTAMP, default NOW()).

**cameras** — id (VARCHAR 50, PK), name (VARCHAR 100), rtsp_url (VARCHAR 500, NOT NULL), camera_type (VARCHAR 20, NOT NULL, default 'cctv'), floor (INTEGER, nullable), is_active (BOOLEAN, default TRUE).

**scoring_config** — activity (VARCHAR 50, PK), weight (FLOAT, NOT NULL), min_dwell_seconds (INTEGER, default 120), description (TEXT, nullable). Seed with default weights: coding 1.0, collaborating 1.5, mentoring 2.0, presenting 2.0, networking 1.2, helping_others 1.8, sponsor_engagement 1.0, eating 0, resting 0, idle 0.

**sponsors** — id (UUID, PK), name (VARCHAR 255, NOT NULL), tier (VARCHAR 50, nullable), booth_zone_id (UUID, nullable, FK → zones), logo_url (VARCHAR 500, nullable), contact_email (VARCHAR 255, nullable).

**sponsor_engagement** — sponsor_id (UUID, FK → sponsors) + hour_bucket (TIMESTAMP) as composite PK. unique_visitors (INTEGER, default 0), total_visits (INTEGER, default 0), avg_dwell_seconds (FLOAT, default 0), return_visitors (INTEGER, default 0).

**heatmap_snapshots** — id (BIGSERIAL, PK), timestamp (TIMESTAMP, NOT NULL), zone_occupancy (JSONB, NOT NULL), total_active (INTEGER, nullable), energy_level (FLOAT, nullable).

**users** — id (UUID, PK), username (VARCHAR 100, UNIQUE, NOT NULL), password_hash (VARCHAR 255, NOT NULL), role (VARCHAR 20, NOT NULL, CHECK IN ('admin', 'operator', 'viewer')), created_at (TIMESTAMP, default NOW()).

### Migration approach

Use Alembic with async SQLAlchemy. One initial migration that creates all tables. The scoring_config table gets seeded with default weights as part of the migration (use `op.bulk_insert`).

### SQLAlchemy models

Define all models in `backend/db/models.py` using SQLAlchemy 2.0 declarative style with `Mapped` type annotations. Use `AsyncSession` for all runtime operations.

### Database connection

`backend/db/database.py` — create async engine with asyncpg, session factory, and a `get_db` dependency for FastAPI. Connection pool: min 5, max 20.

---

## Section 3: Redis Client Setup

### What to build

`backend/db/redis_client.py` — async Redis client using the `redis` Python package with `redis.asyncio`. Connection to Redis container via REDIS_URL from environment. A `get_redis` dependency for FastAPI.

Define helper functions that encapsulate the Redis data patterns (these will be called by later phases but the functions exist now):

- `update_leaderboard(participant_id: str, score: float)` — ZADD
- `get_leaderboard(limit: int) -> list` — ZREVRANGE with scores
- `update_participant_state(participant_id: str, zone: str, activity: str, score: float)` — HSET
- `get_participant_state(participant_id: str) -> dict` — HGETALL
- `update_zone_occupancy(zone_name: str, count: int)` — HSET
- `get_zone_occupancy() -> dict` — HGETALL
- `push_activity_event(event: dict)` — XADD to activity_stream
- `read_activity_events(last_id: str, count: int) -> list` — XREAD from activity_stream

These are wrappers. They don't do business logic. They encapsulate Redis commands so other code never calls raw Redis commands directly.

---

## Section 4: Configuration Management

### What to build

`backend/config.py` — Pydantic BaseSettings class that loads from environment variables. All configuration centralized here. No config scattered across files.

Fields: DATABASE_URL, REDIS_URL, JWT_SECRET, JWT_EXPIRY_HOURS (default 24), FAISS_INDEX_PATH, MODELS_DIR, GCS_BUCKET, LOG_LEVEL (default INFO), FACE_SIMILARITY_THRESHOLD (default 0.5), SCORING_FLUSH_INTERVAL (default 60), HEATMAP_SNAPSHOT_INTERVAL (default 300), MAX_REGISTRATION_STATIONS (default 10).

`configs/cameras.yaml` — camera definitions (id, name, rtsp_url, floor). Empty/example for now, populated during venue setup.

`configs/zones.yaml` — zone definitions (name, type, camera_id, polygon coordinates, floor, capacity). Empty/example for now.

`configs/scoring.yaml` — scoring weights (matches the scoring_config DB table, used as fallback/override).

---

## Section 5: Authentication + Authorization

### What to build

JWT-based auth for all API endpoints. Three roles: admin, operator, viewer.

**User creation** — CLI command only (no registration endpoint). `python -m backend.cli create-user --username bhargavi --password xxx --role admin`. Hashes password with bcrypt (12 rounds), inserts into users table.

**Login endpoint** — `POST /api/v1/auth/login`. Accepts `{username, password}`. Validates against bcrypt hash. Returns `{token, role, expires_at}`. Sets httpOnly cookie for browser-based dashboard access.

**Auth middleware** — FastAPI dependency `get_current_user` that extracts JWT from Authorization header (Bearer) or cookie. Decodes with python-jose. Returns user object with id, username, role. Returns 401 if missing/invalid/expired.

**Permission decorator/dependency** — `require_role(roles: list[str])` dependency that checks the current user's role against allowed roles. Returns 403 if insufficient.

**Endpoint permission mapping:**
- POST /register → admin, operator
- GET /participants → admin, operator
- DELETE /participants/{id} → admin only
- GET /scores/* → admin, operator, viewer
- PUT /config/* → admin only
- GET /export/* → admin only

**No signup endpoint. No password reset. No email verification.** Accounts are created via CLI before the event. This is an internal tool.

---

## Section 6: Face Registration Pipeline

### What to build

The core feature of Phase 1. An endpoint and UI that lets registration staff capture a participant's face, generate an embedding, and store it.

**SCRFD face detector** — `backend/core/face_detector.py`. Loads `scrfd_10g.onnx` via ONNX Runtime with CUDAExecutionProvider (falls back to CPUExecutionProvider if no GPU). Method: `detect(image: np.ndarray) -> list[Face]` where Face contains bbox, confidence, and 5 facial landmarks.

**ArcFace face recognizer** — `backend/core/face_recognizer.py`. Loads `arcface_r100.onnx` via ONNX Runtime. Method: `embed(aligned_face: np.ndarray) -> np.ndarray` returns a 512-dim L2-normalized embedding vector. Face alignment: use the 5 landmarks from SCRFD to compute an affine transform to 112x112 aligned crop before embedding.

**FAISS face matcher** — `backend/core/face_matcher.py`. Wraps a FAISS IndexFlatIP index. Methods:
- `add(embedding: np.ndarray) -> int` — adds embedding, returns index position. Thread-safe via threading.Lock.
- `search(embedding: np.ndarray, k: int = 1) -> tuple[float, int]` — returns (similarity, index_position). Thread-safe for reads (FAISS reads are safe).
- `save(path: str)` — persists index to disk.
- `load(path: str)` — loads index from disk.
- `count() -> int` — returns number of stored embeddings.

An `embedding_map.json` file maps FAISS index positions to participant UUIDs. Loaded into memory on startup, saved alongside the FAISS index.

**Registration endpoint** — `POST /api/v1/register`. Accepts multipart form: photo (JPEG/PNG file), name, email (optional), team_name, track, skills (comma-separated string), consent_confirmed (boolean, must be true). Flow:
1. Validate required fields and consent
2. Read photo bytes, decode to numpy array
3. Run SCRFD face detection
4. If no face detected → 400 "No face detected in photo"
5. If multiple faces detected → 400 "Multiple faces detected, please capture one person at a time"
6. Align the detected face using landmarks
7. Run ArcFace to get 512-dim embedding
8. Search FAISS for duplicates (similarity > 0.6 → 409 "Already registered as {name}")
9. Add embedding to FAISS (behind write lock)
10. Save registration photo to data/faces/{participant_id}.jpg
11. Create participant record in PostgreSQL
12. Create initial scores record (all zeros)
13. Save FAISS index to disk (every 10 registrations)
14. Return 201 with participant profile

**Participant endpoints:**
- `GET /api/v1/participants` — paginated list with search (name, team, track filters)
- `GET /api/v1/participants/{id}` — single participant with score data
- `DELETE /api/v1/participants/{id}` — opt-out: remove embedding from FAISS, anonymize in DB, delete photo

---

## Section 7: Frontend Scaffold + Registration UI

### What to build

React app with Vite, TypeScript, Tailwind. Router with all page shells (just page title + "Coming in Phase N" placeholder for non-Phase-1 pages). Fully functional registration page.

**App shell:**
- Login page (functional — calls POST /auth/login, stores JWT)
- Auth context provider (checks token, redirects to login if expired)
- Layout with sidebar navigation: CCTV Wall, Leaderboard, Heatmap, Analytics, Sponsors, Registration, Settings
- All pages except Login and Registration show "Coming in Phase {N}" placeholder
- Responsive: desktop (≥1024px) gets sidebar, tablet (≥768px) gets registration form only

**Registration page (fully functional):**
- Camera capture: uses browser's navigator.mediaDevices.getUserMedia to access tablet/laptop webcam
- Live camera preview showing what the webcam sees
- "Capture" button freezes the frame
- Form fields: name (required), email, team name (required), track (dropdown: AI/ML, Web3, DevTools, FinTech, Health, Open), skills (tag input)
- Consent checkbox: "Participant informed about camera tracking. Consent confirmed."
- "Register" button: sends multipart form to POST /api/v1/register
- Success state: shows "Registered: {name}. Total registered: {count}."
- Error states: "No face detected" / "Already registered" / "Missing fields" displayed clearly
- After success, form resets for next participant (continuous registration flow)
- Counter in corner showing total registered participants (polls GET /participants?count_only=true)

**API client:**
- `dashboard/src/utils/api.ts` — axios or fetch wrapper with base URL from env, JWT injection, error handling
- Types defined in `dashboard/src/types/index.ts` for Participant, Score, Zone, Camera, etc.

---

## Section 8: Logging + Error Tracking

### What to build

Structured JSON logging via loguru across all backend services. Consistent error handling patterns.

**Logging setup** — `backend/main.py` on startup:
- Configure loguru: JSON format with timestamp, level, service name, message, and extra fields
- Log level from config (default INFO, configurable via LOG_LEVEL env var)
- Log to stdout (Docker captures it via `docker logs`)
- Also log to file: `/app/logs/spatialscore.log`, rotated daily, max 1GB

**Structured log events for Phase 1:**
- `INFO` — "Registration: {name}, team={team}, embedding_id={id}" on successful registration
- `WARNING` — "Duplicate face detected: similarity={sim}, existing={name}" on duplicate attempt
- `WARNING` — "No face detected in registration photo" on bad photo
- `ERROR` — "Database connection failed: {error}" on DB issues
- `ERROR` — "FAISS index save failed: {error}" on disk issues
- `INFO` — "Health check: all services healthy" every 60 seconds

**Error handling middleware** — FastAPI exception handlers:
- `HTTPException` → return structured error response `{"error": message, "code": code}`
- `ValidationError` (Pydantic) → return 422 with field-level errors
- Unhandled exceptions → log full traceback, return 500 `{"error": "Internal server error", "code": "INTERNAL_ERROR"}`
- Never expose stack traces to the client

**Request logging middleware** — log every API request: method, path, status code, response time in ms. INFO level. Skip health check endpoints to avoid noise.

---

## Section 9: Health Checks + Monitoring Foundation

### What to build

A health check endpoint and basic system metrics collection that later phases will extend.

**Health endpoint** — `GET /api/v1/health` (no auth required). Checks:
- PostgreSQL: execute `SELECT 1`
- Redis: execute `PING`
- FAISS index: verify loaded and `index.ntotal >= 0`
- Disk space: verify >10GB free on /app/data
- Response: `{"status": "healthy"|"degraded"|"unhealthy", "checks": {...}, "uptime_seconds": N}`

**Metrics endpoint** — `GET /api/v1/metrics` (admin only). Returns:
- `total_registered`: count of participants
- `faiss_index_size`: number of embeddings
- `redis_memory_used_mb`: Redis INFO memory
- `postgres_connection_pool`: active/idle connections
- `uptime_seconds`: since API server started

These endpoints will be extended in later phases to include camera status, scoring lag, GPU usage, etc.

---

## Section 10: Security Foundation

### What to build

Security patterns that every phase inherits.

**CORS** — allow origins: `http://localhost:3000` (dev) and `https://spatialscore.buildathon.co` (prod, if domain set up). No wildcard.

**Security headers middleware** — set on all responses:
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Cache-Control: no-store (for API responses with PII)

**Input validation** — Pydantic models on every endpoint. File upload validation: accept only image/jpeg and image/png, max 5MB, validate file magic bytes (not just extension).

**Rate limiting** — slowapi middleware:
- Global: 100 requests/minute per IP
- POST /register: 10/minute per IP (physical bottleneck is slower anyway)
- POST /auth/login: 5/minute per IP (prevent brute force)
- GET /health: exempt from rate limiting

**Secrets management** — all secrets (DB_PASSWORD, JWT_SECRET) loaded from .env, never hardcoded. JWT_SECRET must be at least 32 characters. The API refuses to start if JWT_SECRET is "changeme" or shorter than 32 chars.

**.gitignore** — include: .env, __pycache__, node_modules, .DS_Store, *.onnx, *.pt, data/faces/, data/faiss/, logs/

---

## Section 11: CI/CD Foundation

### What to build

GitHub Actions workflow that runs on every push and PR.

**`.github/workflows/ci.yml`:**
- **lint job:** ruff check backend/, cd dashboard && npm run lint
- **test-backend job:** starts postgres + redis services, runs pytest backend/tests/ with coverage
- **test-frontend job:** cd dashboard && npm ci && npm test
- **build-docker job** (depends on lint + tests passing): docker compose build, docker compose up -d, sleep 10, curl health endpoint, docker compose down

**Tests to write in Phase 1:**
- `tests/unit/test_face_detector.py` — verify SCRFD loads (mock ONNX session), returns face objects with expected fields
- `tests/unit/test_face_recognizer.py` — verify ArcFace loads, returns 512-dim normalized embedding
- `tests/unit/test_face_matcher.py` — verify FAISS add, search, save, load, thread safety
- `tests/integration/test_registration.py` — POST /register with a test face image, verify 201 response, verify participant in DB, verify embedding in FAISS
- `tests/integration/test_auth.py` — login with valid/invalid credentials, access protected endpoint with/without token, role-based access

Keep tests minimal but meaningful. Each test should verify one behavior. No mocking of the database — use the real test PostgreSQL instance.

---

## Section 12: GCP Setup Script

### What to build

`scripts/setup_gcp.sh` — documented shell script that configures the GCE VM from scratch. Not run by Docker or CI — this is a manual one-time setup script.

Steps the script should cover (documented with comments, executable):
1. Install NVIDIA drivers (driver 550)
2. Install Docker + Docker Compose
3. Install NVIDIA Container Toolkit
4. Configure Docker to use nvidia runtime by default
5. Clone the repo
6. Copy .env.example to .env, prompt for secrets
7. Run scripts/download_models.sh to fetch model weights
8. Create data directories (data/faces, data/faiss, data/venue, data/exports, data/backups, logs)
9. Run docker compose up -d
10. Run initial database migration
11. Create admin user via CLI
12. Print health check result

---

## What NOT to Build in This Phase

- No camera workers — no DEIMv2 inference, no RTSP processing, no frame-by-frame detection (Phase 2)
- No supervision integration — no ByteTrack, no PolygonZone, no annotators (Phase 2)
- No scoring engine — no Redis Stream consumption, no score calculation (Phase 3)
- No CCTV wall — no camera grid, no bounding boxes, no click-to-inspect (Phase 3)
- No WebSocket channels — no live updates (Phase 3)
- No heatmap — no zone overlays, no floor plan visualization (Phase 4)
- No energy graph — no activity over time chart (Phase 4)
- No alerts — no zone capacity warnings (Phase 4)
- No sponsor tracking — no LineZone, no engagement reports (Phase 5)
- No PDF export — no report generation (Phase 5)
- No load testing — no simulated streams (Phase 6)

---

## Acceptance Criteria

- [ ] `docker compose up` starts all services (mediamtx, postgres, redis, api, dashboard) without errors
- [ ] `curl http://localhost:8000/api/v1/health` returns `{"status": "healthy"}` with all checks passing
- [ ] `python -m backend.cli create-user --username test --password testpass123 --role admin` creates a user in the database
- [ ] `POST /api/v1/auth/login` with valid credentials returns a JWT token
- [ ] `POST /api/v1/auth/login` with invalid credentials returns 401
- [ ] `GET /api/v1/participants` without token returns 401
- [ ] `GET /api/v1/participants` with valid token returns `{"data": [], "pagination": {...}}`
- [ ] `POST /api/v1/register` with a JPEG containing a face returns 201 with participant data including embedding_id
- [ ] `POST /api/v1/register` with the same face again returns 409 "Already registered"
- [ ] `POST /api/v1/register` with an image containing no face returns 400 "No face detected"
- [ ] `POST /api/v1/register` without consent_confirmed=true returns 422
- [ ] After registering 3 participants, `GET /api/v1/participants` returns 3 items
- [ ] After registering 3 participants, FAISS index on disk contains 3 embeddings
- [ ] `DELETE /api/v1/participants/{id}` removes the embedding from FAISS and anonymizes the DB record
- [ ] Restarting the api container preserves registered participants (PostgreSQL) and face embeddings (FAISS from disk)
- [ ] Opening http://localhost:3000 in a browser shows the login page
- [ ] Logging in redirects to the dashboard with sidebar navigation
- [ ] Registration page shows live camera preview and registration form
- [ ] Registering via the UI successfully creates a participant (end-to-end browser test)
- [ ] Rate limiting blocks the 11th registration request within 1 minute from the same IP
- [ ] All pytest tests pass (unit + integration)
- [ ] GitHub Actions CI pipeline passes (lint + test + build)

---

## How to Give This to Cursor

Save this file as `docs/PHASE_1_SPEC.md`. Then:

```
Read .cursorrules, PROJECT.md, and docs/PHASE_1_SPEC.md. This is Phase 1 of SpatialScore.
Create a detailed implementation plan first: list every file you will create, what each
contains, and the order you will work in. Present the plan and wait for my approval
before writing any code.
```

---

## After This Phase

Once all acceptance criteria pass, proceed to Phase 2: Camera Pipeline + Identity. That phase adds:
- Camera worker processes consuming RTSP via MediaMTX
- DEIMv2-wholebody49 ONNX inference with 49 keypoints
- supervision ByteTrack for person tracking
- supervision PolygonZone for zone classification
- Face recognition linking tracks to registered identities
- Activity events flowing into Redis Stream
