# SYSTEM SPECIFICATION
# SpatialScore — Complete Engineering Specification
# Version 1.0 | June 2026

---

## TABLE OF CONTENTS

1. System Design Overview
2. System Architecture
3. Frontend Specification
4. API Specification
5. Backend Logic
6. Database & Storage
7. Authentication & Permissions
8. Hosting & Cloud Infrastructure
9. CI/CD & Version Control
10. Security
11. Rate Limiting
12. Caching & CDN
13. Error Tracking & Logging
14. Monitoring & Alerts
15. Testing Strategy
16. Scaling Strategy
17. Disaster Recovery & Backup
18. Performance Budgets
19. Data Privacy & Compliance
20. Operational Runbook

---

## 1. SYSTEM DESIGN OVERVIEW

### 1.1 Design Philosophy

SpatialScore runs entirely on a single Google Cloud GPU VM. Camera feeds are relayed from the venue over the internet via ffmpeg/RTMP. All ML inference, data processing, scoring, and dashboard rendering happen in the cloud. The only hardware at the venue is the CCTV cameras and a relay laptop running ffmpeg.

Design constraints that drive every decision:

- **Internet-dependent:** Venue must have 60+ Mbps sustained upload for 10-13 camera streams. If internet drops, tracking pauses until it recovers.
- **Single VM simplicity:** Everything runs in Docker Compose on one GCE g2-standard-8 (NVIDIA L4, 24GB VRAM). No distributed systems, no Kafka, no managed services. PostgreSQL and Redis in Docker on the VM.
- **Zero venue hardware beyond cameras:** No GPU, no server, no special equipment at the venue. Just IP cameras + a laptop running ffmpeg as a relay.
- **Single point of failure tolerance:** If any one camera feed drops, the system continues tracking via remaining cameras. If the scoring engine crashes, it recovers from the last Redis checkpoint.
- **24-hour continuous operation:** The system must run the entire hackathon without restart, without memory leaks, without degradation.

### 1.2 High-Level Data Flow

```
Physical World
    │
    ▼
[Cameras + Drones] ──RTSP──▶ [Camera Workers] ──Redis Stream──▶ [Scoring Engine]
                                    │                                    │
                                    ▼                                    ▼
                              [FAISS Index]                      [PostgreSQL + Redis]
                              (face matching)                    (scores + state)
                                                                        │
                                                                        ▼
                                                              [FastAPI Server]
                                                                  │       │
                                                              REST    WebSocket
                                                                  │       │
                                                                  ▼       ▼
                                                          [React Dashboard]
                                                          (organizer only)
```

### 1.3 Service Inventory

| Service | Process Type | Instances | Restart Policy |
|---------|-------------|-----------|----------------|
| camera-worker | Python multiprocessing | 1 per camera (4-6) | Auto-restart on crash |
| scoring-engine | Python async | 1 | Auto-restart, recovers from Redis checkpoint |
| heatmap-worker | Python periodic | 1 | Auto-restart |
| api-server | FastAPI/uvicorn | 1 (4 workers) | Auto-restart |
| dashboard | React/nginx | 1 | Auto-restart |
| postgres | PostgreSQL 16 | 1 | Auto-restart, WAL-based recovery |
| redis | Redis 7 | 1 | Auto-restart, AOF persistence |

---

## 2. SYSTEM ARCHITECTURE

### 2.1 Network Topology (Venue → GCP)

```
VENUE (Dallas)                        GOOGLE CLOUD (us-central1-a)
──────────────                        ─────────────────────────────

Camera RTSP streams                   GCE VM: g2-standard-8
(10-13 cameras,                       Public IP: 34.x.x.x
 3 floors)                            
     │                                ┌──────────────────────────┐
     │ local network                  │  port 1935: MediaMTX     │
     ▼                                │  (receives RTMP streams) │
Organizer Laptop                      │                          │
  ffmpeg × 10-13                      │  port 8000: FastAPI      │
  (RTSP → RTMP relay)                 │  (REST + WebSocket API)  │
     │                                │                          │
     │ internet (~60 Mbps up)         │  port 3000: nginx        │
     │ RTMP push to VM IP             │  (React dashboard)       │
     └──────────────────────────────→ │                          │
                                      │  port 22: SSH            │
                                      │  (admin only)            │
                                      └──────────────────────────┘

All services communicate via Docker internal network (172.17.0.0/16).
No inter-service traffic leaves the VM.
```

### 2.2 Container Architecture

```yaml
# docker-compose.yml — runs on GCE g2-standard-8 VM
services:
  mediamtx:
    image: bluenviron/mediamtx:latest
    ports: ["1935:1935", "8554:8554"]
    volumes: [./configs/mediamtx.yml:/mediamtx.yml]
    restart: always
    # Receives RTMP from venue laptop, re-exposes as local RTSP

  postgres:
    image: postgres:16-alpine
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: spatialscore
      POSTGRES_USER: spatialscore
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    restart: always
    healthcheck:
      test: pg_isready -U spatialscore
      interval: 10s

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
    volumes: [redisdata:/data]
    restart: always
    healthcheck:
      test: redis-cli ping
      interval: 10s

  api:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [postgres, redis]
    environment:
      DATABASE_URL: postgresql+asyncpg://spatialscore:${DB_PASSWORD}@postgres:5432/spatialscore
      REDIS_URL: redis://redis:6379
      JWT_SECRET: ${JWT_SECRET}
      GCS_BUCKET: spatialscore-data
    restart: always
    deploy:
      resources:
        limits: { cpus: "4", memory: 4G }

  camera-worker-01:
    build: ./backend
    command: python -m workers.camera_worker --camera-id CAM-01 --rtsp-url rtsp://mediamtx:8554/cam01
    depends_on: [redis, mediamtx]
    runtime: nvidia
    environment:
      REDIS_URL: redis://redis:6379
    restart: always
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]

  # camera-worker-02 through camera-worker-13 (same pattern, different camera IDs)

  scoring-engine:
    build: ./backend
    command: python -m workers.scoring_worker
    depends_on: [postgres, redis]
    environment:
      DATABASE_URL: postgresql+asyncpg://spatialscore:${DB_PASSWORD}@postgres:5432/spatialscore
      REDIS_URL: redis://redis:6379
    restart: always

  heatmap-worker:
    build: ./backend
    command: python -m workers.heatmap_worker
    depends_on: [redis, postgres]
    environment:
      DATABASE_URL: postgresql+asyncpg://spatialscore:${DB_PASSWORD}@postgres:5432/spatialscore
      REDIS_URL: redis://redis:6379
    restart: always

  dashboard:
    build: ./dashboard
    ports: ["3000:80"]
    restart: always

volumes:
  pgdata:
  redisdata:
```

### 2.3 Inter-Service Communication

| From | To | Protocol | Data |
|------|----|----------|------|
| Camera → Camera Worker | RTSP over TCP | H.264 video stream | Raw video frames |
| Camera Worker → Redis | Redis Stream (XADD) | JSON | `{participant_id, zone, activity, bbox, keypoints, cam, timestamp}` |
| Camera Worker → FAISS | In-process function call | numpy array | 512-dim face embedding → participant_id |
| Scoring Engine → Redis Stream | Redis Stream (XREAD) | JSON | Consumes activity events |
| Scoring Engine → PostgreSQL | SQLAlchemy async | SQL | Activity log inserts, score updates |
| Scoring Engine → Redis | Redis commands | Sorted set, hash | Leaderboard update, state update |
| API Server → PostgreSQL | SQLAlchemy async | SQL | Query participants, scores, analytics |
| API Server → Redis | Redis commands | Read | Current state, leaderboard, heatmap |
| API Server → Dashboard | WebSocket + REST | JSON | Real-time updates + API responses |

### 2.4 Process Lifecycle

```
STARTUP SEQUENCE:
1. PostgreSQL starts, runs migrations (Alembic)
2. Redis starts, loads AOF if exists
3. API server starts, loads FAISS index from disk
4. Camera workers start, each:
   a. Loads SCRFD + ArcFace ONNX models into GPU memory
   b. Loads YOLO11-Pose model
   c. Connects to RTSP stream
   d. Begins frame processing loop
5. Scoring engine starts, begins consuming Redis Stream
6. Heatmap worker starts, begins periodic snapshots
7. Dashboard nginx starts

SHUTDOWN SEQUENCE:
1. Camera workers stop frame processing, flush pending events
2. Scoring engine processes remaining events, writes final scores
3. FAISS index saved to disk
4. Redis AOF flush
5. PostgreSQL clean shutdown
```

---

## 3. FRONTEND SPECIFICATION

### 3.1 Tech Stack

| Layer | Technology | Justification |
|-------|-----------|---------------|
| Framework | React 18 + TypeScript | Component-based, massive ecosystem, strong typing |
| Build | Vite 5 | Fast HMR, ESBuild bundling, tree-shaking |
| Styling | Tailwind CSS 3 | Utility-first, responsive, no custom CSS files |
| Charts | Recharts 2.x | React-native charts, composable, SSR-compatible |
| Heatmap | D3.js 7 | Programmable SVG for spatial overlays on floor plan |
| State | Zustand | Lightweight global state for WebSocket data |
| Data Fetching | @tanstack/react-query 5 | Caching, background refetch, stale-while-revalidate |
| WebSocket | Native WebSocket API + reconnecting-websocket | Auto-reconnect on network drops |
| Routing | React Router 6 | Client-side routing between dashboard views |
| Icons | Lucide React | Consistent icon set |
| Date/Time | date-fns | Lightweight date formatting |
| PDF Export | react-pdf/renderer | Client-side PDF generation for sponsor reports |

### 3.2 Page Architecture

```
/login                    → Login.tsx (JWT auth)
/                         → CCTVWall.tsx (primary — camera grid + click-to-inspect)
/leaderboard              → Leaderboard.tsx (sortable, filterable, compare mode)
/participant/:id          → ParticipantProfile.tsx (full timeline + radar chart)
/heatmap                  → Heatmap.tsx (per-floor zone overlays)
/analytics                → Analytics.tsx (energy graph, zone utilization)
/sponsors                 → SponsorReports.tsx (per-sponsor engagement)
/sponsors/:id/report      → SponsorReport.tsx (single sponsor PDF view)
/registration             → Registration.tsx (tablet check-in, parallel stations)
/settings                 → Settings.tsx (cameras, zones, scoring config)
/settings/cameras         → CameraSettings.tsx
/settings/zones           → ZoneEditor.tsx (polygon drawing tool)
/settings/scoring         → ScoringConfig.tsx (weight adjustment)
```

### 3.3 Component Tree

```
App
├── AuthProvider (JWT context)
├── WebSocketProvider (connection + reconnect logic)
│   ├── useLeaderboardWS() — subscribes to /ws/leaderboard
│   ├── useHeatmapWS() — subscribes to /ws/heatmap
│   ├── useAlertsWS() — subscribes to /ws/alerts
│   └── useParticipantWS(id) — subscribes to /ws/participant/{id}
├── QueryProvider (react-query client)
└── Router
    ├── CommandCenter
    │   ├── LiveStatsPanel (active counts by activity)
    │   ├── VenueHeatmap (D3 overlay on floor plan SVG)
    │   ├── EnergyGraph (Recharts LineChart)
    │   ├── ZoneUtilization (Recharts BarChart)
    │   ├── AlertsFeed (live alert stream)
    │   ├── MiniLeaderboard (top 10)
    │   └── ParticipantSearch (search bar → lookup modal)
    ├── Leaderboard
    │   ├── SortControls (sort by: total, coding, mentoring, etc.)
    │   ├── FilterControls (filter by: team, track, tag)
    │   ├── ParticipantTable (paginated, clickable rows)
    │   └── CompareMode (side-by-side comparison)
    ├── ParticipantLookup
    │   ├── CurrentStatus (location, activity, time in zone)
    │   ├── ScoreCard (total score, rank)
    │   ├── RadarChart (activity distribution)
    │   ├── ActivityTimeline (hour-by-hour blocks)
    │   ├── SponsorVisits (booth engagement)
    │   └── TeamsVisited (cross-team tracking)
    ├── LiveTracking
    │   ├── CameraGrid (2x2 or 3x2 camera layout)
    │   ├── CameraFeed (MJPEG/HLS stream with bbox overlays)
    │   └── TrackingOverlay (names + activities rendered on video)
    ├── Registration
    │   ├── CameraCapture (webcam access for face capture)
    │   ├── RegistrationForm (name, team, track, skills)
    │   ├── ConsentCheckbox
    │   └── ConfirmationPanel (registration success + count)
    └── Settings
        ├── CameraManager (CRUD cameras, test streams)
        ├── ZoneEditor (polygon drawing on camera frame)
        └── ScoringEditor (weight sliders + preview)
```

### 3.4 WebSocket Message Formats

```typescript
// Leaderboard update (every 30s)
interface LeaderboardUpdate {
  type: "leaderboard";
  data: Array<{
    participant_id: string;
    name: string;
    team: string;
    score: number;
    rank: number;
    current_activity: string;
    current_zone: string;
    tags: string[];
  }>;
  timestamp: string;
}

// Heatmap update (every 10s)
interface HeatmapUpdate {
  type: "heatmap";
  zones: Record<string, {
    occupancy: number;
    capacity: number;
    percentage: number;
  }>;
  total_active: number;
  energy_level: number; // 0-1
  timestamp: string;
}

// Alert
interface Alert {
  type: "alert";
  severity: "info" | "warning" | "critical";
  message: string;
  zone?: string;
  timestamp: string;
}

// Participant live update
interface ParticipantUpdate {
  type: "participant_update";
  participant_id: string;
  zone: string;
  activity: string;
  score: number;
  rank: number;
  timestamp: string;
}
```

### 3.5 Responsive Design

| Breakpoint | Target Device | Layout |
|-----------|---------------|--------|
| ≥1440px | Organizer desktop | Full command center with sidebar |
| ≥1024px | Organizer laptop | Condensed sidebar, scrollable panels |
| ≥768px | Registration tablet | Registration form only (iPad-sized) |
| <768px | Not supported | Redirect to "use desktop" message |

### 3.6 Offline Resilience

The dashboard is a local network app — not internet-dependent. However, WebSocket connections can drop within the venue network:

- **reconnecting-websocket** library auto-reconnects with exponential backoff (1s, 2s, 4s, 8s max)
- React-query uses `staleTime: 30000` — shows cached data during reconnect
- Visual indicator: connection status bar at top ("Connected" / "Reconnecting..." / "Offline")
- On reconnect, full state refresh via REST before resuming WebSocket

---

## 4. API SPECIFICATION

### 4.1 API Conventions

| Convention | Detail |
|-----------|--------|
| Base URL | `http://10.0.2.100:8000/api/v1` |
| Content Type | `application/json` |
| Auth | Bearer JWT in `Authorization` header |
| Pagination | `?page=1&per_page=50` (default 50, max 200) |
| Sorting | `?sort_by=total_score&sort_order=desc` |
| Filtering | `?track=ai_ml&team=team_alpha&tag=mentor` |
| Error format | `{"error": "message", "code": "ERROR_CODE", "details": {...}}` |
| Timestamps | ISO 8601 UTC (`2026-07-15T02:34:12Z`) |
| IDs | UUID v4 |

### 4.2 Endpoint Specification

#### Registration

```
POST /api/v1/register
  Body: multipart/form-data
    - photo: file (JPEG/PNG, face image)
    - name: string (required)
    - email: string (optional)
    - team_name: string (required)
    - track: string (required, enum: ai_ml, web3, devtools, fintech, health, open)
    - skills: string[] (optional)
    - consent_confirmed: boolean (required, must be true)
  Response: 201
    {
      "participant_id": "uuid",
      "name": "Riya Sharma",
      "team_name": "Team Alpha",
      "track": "ai_ml",
      "embedding_stored": true,
      "registered_at": "2026-07-15T18:02:34Z"
    }
  Errors:
    400 — No face detected in photo
    400 — Multiple faces detected
    409 — Duplicate face (already registered)
    422 — Missing required fields
```

#### Participants

```
GET /api/v1/participants
  Query: ?page=1&per_page=50&search=riya&track=ai_ml&team=alpha
  Response: 200
    {
      "participants": [...],
      "total": 187,
      "page": 1,
      "per_page": 50
    }

GET /api/v1/participants/{id}
  Response: 200
    {
      "id": "uuid",
      "name": "Riya Sharma",
      "team_name": "Team Alpha",
      "track": "ai_ml",
      "skills": ["python", "react"],
      "registered_at": "...",
      "current_zone": "Coding Zone A",
      "current_activity": "collaborating",
      "last_seen_at": "...",
      "score": { ... },      // full score breakdown
      "timeline": [ ... ]     // activity timeline
    }

DELETE /api/v1/participants/{id}
  — Removes face embedding from FAISS
  — Anonymizes activity logs (replaces participant_id with hash)
  — Sets opted_out = true
  Response: 204
```

#### Scores

```
GET /api/v1/scores/leaderboard
  Query: ?sort_by=total_score|coding|mentoring|collaborating|networking
         &tag=builder|mentor|collaborator
         &limit=50
  Response: 200
    {
      "leaderboard": [
        {
          "rank": 1,
          "participant_id": "uuid",
          "name": "Arjun Patel",
          "team_name": "Team Beta",
          "total_score": 1204.5,
          "coding_minutes": 480,
          "collaborating_minutes": 180,
          "mentoring_minutes": 90,
          "presenting_minutes": 45,
          "networking_minutes": 60,
          "tags": ["Builder", "Night Owl"],
          "current_zone": "Coding Zone A",
          "current_activity": "coding"
        },
        ...
      ],
      "total_participants": 187,
      "event_duration_hours": 10.5
    }

GET /api/v1/scores/{participant_id}
  Response: 200
    {
      "participant_id": "uuid",
      "total_score": 918.0,
      "rank": 7,
      "activity_breakdown": {
        "coding": {"minutes": 240, "points": 240, "percentage": 33},
        "collaborating": {"minutes": 180, "points": 270, "percentage": 25},
        "mentoring": {"minutes": 120, "points": 240, "percentage": 17},
        "presenting": {"minutes": 60, "points": 120, "percentage": 8},
        "networking": {"minutes": 60, "points": 72, "percentage": 8},
        "helping_others": {"minutes": 60, "points": 108, "percentage": 8},
        "idle": {"minutes": 30, "points": 0, "percentage": 4}
      },
      "tags": ["Builder", "Mentor", "Night Owl"],
      "radar_data": [
        {"axis": "Coding", "value": 0.33},
        {"axis": "Collaborating", "value": 0.25},
        {"axis": "Mentoring", "value": 0.17},
        {"axis": "Presenting", "value": 0.08},
        {"axis": "Networking", "value": 0.08}
      ]
    }

GET /api/v1/scores/{participant_id}/timeline
  Response: 200
    {
      "timeline": [
        {"hour": "18:00", "zone": "Coding Zone A", "activity": "coding", "minutes": 60},
        {"hour": "19:00", "zone": "Coding Zone A", "activity": "coding", "minutes": 60},
        ...
      ]
    }

GET /api/v1/scores/compare
  Query: ?ids=uuid1,uuid2,uuid3
  Response: 200
    {
      "participants": [
        {"id": "uuid1", "name": "...", "score": {...}},
        {"id": "uuid2", "name": "...", "score": {...}},
        ...
      ]
    }
```

#### Live Tracking

```
GET /api/v1/tracking/active
  Response: 200
    {
      "active_participants": [
        {
          "participant_id": "uuid",
          "name": "Riya Sharma",
          "zone": "Coding Zone A",
          "camera_id": "CAM-03",
          "activity": "collaborating",
          "since": "2026-07-15T00:34:12Z"
        },
        ...
      ],
      "total_active": 187
    }

GET /api/v1/tracking/{participant_id}
  Response: 200
    {
      "participant_id": "uuid",
      "name": "Riya Sharma",
      "zone": "Coding Zone A",
      "camera_id": "CAM-03",
      "activity": "collaborating",
      "bbox": [x1, y1, x2, y2],
      "since": "...",
      "last_updated": "..."
    }

GET /api/v1/tracking/zone/{zone_id}
  Response: 200
    {
      "zone": "Coding Zone A",
      "occupancy": 34,
      "capacity": 40,
      "participants": [...]
    }
```

#### Analytics

```
GET /api/v1/analytics/heatmap
  Response: 200
    {
      "zones": {
        "Coding Zone A": {"occupancy": 34, "capacity": 40, "pct": 85},
        ...
      },
      "energy_level": 0.73,
      "total_active": 187,
      "timestamp": "..."
    }

GET /api/v1/analytics/energy
  Query: ?from=2026-07-15T18:00:00Z&to=2026-07-16T06:00:00Z
  Response: 200
    {
      "data_points": [
        {"timestamp": "18:00", "energy": 0.45, "active": 150},
        {"timestamp": "18:30", "energy": 0.62, "active": 172},
        ...
      ]
    }

GET /api/v1/analytics/zones
  Query: ?from=...&to=...
  Response: 200
    {
      "zones": {
        "Coding Zone A": [
          {"timestamp": "18:00", "occupancy": 20},
          {"timestamp": "18:30", "occupancy": 28},
          ...
        ],
        ...
      }
    }
```

#### Sponsors

```
GET /api/v1/sponsors/{id}/report
  Response: 200
    {
      "sponsor": {"id": "uuid", "name": "Lovable", "tier": "gold"},
      "metrics": {
        "unique_visitors": 247,
        "total_visits": 312,
        "avg_dwell_seconds": 252,
        "return_visitors": 38,
        "peak_hour": "14:00"
      },
      "hourly_traffic": [...],
      "visitor_breakdown": {
        "by_track": {"ai_ml": 42, "web3": 23, ...},
        "by_team_size": {"solo": 15, "small": 45, "large": 40}
      }
    }

GET /api/v1/sponsors/{id}/report/pdf
  Response: 200 (application/pdf)
```

#### Configuration

```
GET /api/v1/config/scoring
  Response: 200
    {
      "weights": {
        "coding": {"weight": 1.0, "min_dwell_seconds": 120},
        "collaborating": {"weight": 1.5, "min_dwell_seconds": 120},
        ...
      }
    }

PUT /api/v1/config/scoring
  Body: {"weights": {"coding": {"weight": 1.2}}}
  — Only updates specified fields
  — Triggers score recalculation for all participants
  Response: 200

POST /api/v1/cameras
  Body: {"name": "CAM-05", "rtsp_url": "rtsp://...", "camera_type": "cctv"}
  Response: 201

GET /api/v1/cameras
  Response: 200
    {
      "cameras": [
        {"id": "CAM-01", "name": "Coding Zone A", "status": "active", "fps": 9.8, "uptime": "10h 32m"},
        ...
      ]
    }
```

#### Export

```
GET /api/v1/export/scores
  Response: 200 (text/csv)
  — All participants with full score breakdown

GET /api/v1/export/trajectories
  Query: ?format=opentraj|json
  Response: 200 (text/csv or application/json)
  — Timestamped (x, y, vx, vy, activity) per participant in OpenTraj format

GET /api/v1/export/activity-logs
  Query: ?participant_id=uuid&from=...&to=...
  Response: 200 (application/json)
```

### 4.3 WebSocket Endpoints

```
ws://10.0.2.100:8000/ws/leaderboard
  Auth: JWT token in query param ?token=xxx
  Push interval: 30 seconds
  Message: LeaderboardUpdate

ws://10.0.2.100:8000/ws/heatmap
  Push interval: 10 seconds
  Message: HeatmapUpdate

ws://10.0.2.100:8000/ws/alerts
  Push: on-event (when alert fires)
  Message: Alert

ws://10.0.2.100:8000/ws/tracking/{camera_id}
  Push interval: 1 second
  Message: Array of tracked person positions for that camera

ws://10.0.2.100:8000/ws/participant/{participant_id}
  Push interval: 30 seconds
  Message: ParticipantUpdate
```

---

## 5. BACKEND LOGIC

### 5.1 Camera Worker Process (1 per camera)

```python
# Pseudocode for camera_worker.py — USES ROBOFLOW SUPERVISION + DEIMv2

import numpy as np
import supervision as sv

class CameraWorker:
    def __init__(self, camera_id, rtsp_url, faiss_index, zone_configs):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.faiss_index = faiss_index
        self.scrfd = onnxruntime.InferenceSession("scrfd_10g.onnx")
        self.arcface = onnxruntime.InferenceSession("arcface_r100.onnx")
        self.deimv2 = load_deimv2("deimv2_s_wholebody49.onnx")  # 49 keypoints per person
        self.redis = Redis()
        self.face_interval = 20  # face recognition every 20 frames (2s at 10fps)
        self.track_to_identity = {}  # sv track_id → participant_id

        # Supervision components
        self.tracker = sv.ByteTrack(
            track_activation_threshold=0.25,
            lost_track_buffer=30,
            minimum_matching_threshold=0.8
        )
        self.smoother = sv.DetectionsSmoother()

        # Polygon zones from config
        self.zones = {}
        for zone_cfg in zone_configs:
            self.zones[zone_cfg["name"]] = {
                "zone": sv.PolygonZone(polygon=np.array(zone_cfg["polygon"])),
                "type": zone_cfg["type"]
            }

        # Sponsor booth entry/exit lines
        self.sponsor_lines = {}
        for line_cfg in zone_configs.get("lines", []):
            self.sponsor_lines[line_cfg["name"]] = sv.LineZone(
                start=sv.Point(*line_cfg["start"]),
                end=sv.Point(*line_cfg["end"])
            )

        # Annotators for organizer CCTV wall view
        self.box_annotator = sv.BoxAnnotator()
        self.label_annotator = sv.LabelAnnotator()
        self.heatmap_annotator = sv.HeatMapAnnotator()
        self.trace_annotator = sv.TraceAnnotator()

    def run(self):
        frame_count = 0
        for frame in sv.get_video_frames_generator(self.rtsp_url):

            # 1. DEIMv2-wholebody49: detect persons + 49 keypoints
            boxes, scores, keypoints_49 = self.deimv2.predict(frame)
            detections = sv.Detections(
                xyxy=boxes,
                confidence=scores,
                data={"keypoints": keypoints_49}  # 49 keypoints per person
            )
            detections = self.tracker.update_with_detections(detections)
            detections = self.smoother.update_with_detections(detections)

            # 2. Face recognition (every N frames)
            if frame_count % self.face_interval == 0:
                faces = self.scrfd.detect(frame)
                for face in faces:
                    embedding = self.arcface.embed(face.aligned_crop)
                    match = self.faiss_index.search(embedding, k=1)
                    if match.distance > 0.5:
                        participant_id = self.id_map[match.index]
                        track_id = self.find_matching_track(face.bbox, detections)
                        if track_id is not None:
                            self.track_to_identity[track_id] = participant_id

            # 3. Zone classification — sv.PolygonZone
            for zone_name, zone_data in self.zones.items():
                in_zone = zone_data["zone"].trigger(detections)
                zone_type = zone_data["type"]

                for i, is_in in enumerate(in_zone):
                    if not is_in:
                        continue
                    track_id = detections.tracker_id[i]
                    participant_id = self.track_to_identity.get(track_id)
                    if participant_id is None:
                        continue

                    # Activity classification using 49 keypoints
                    kps = detections.data["keypoints"][i]  # 49 keypoints
                    activity = self.classify_activity(zone_type, kps)

                    event = {
                        "participant_id": participant_id,
                        "camera_id": self.camera_id,
                        "zone": zone_name,
                        "zone_type": zone_type,
                        "activity": activity,
                        "bbox": detections.xyxy[i].tolist(),
                        "confidence": float(detections.confidence[i]),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    self.redis.xadd("activity_stream", event)

            # 4. Sponsor booth entry/exit
            for sponsor_name, line in self.sponsor_lines.items():
                crossed_in, crossed_out = line.trigger(detections)

            # 5. Update zone occupancy in Redis
            for zone_name, zone_data in self.zones.items():
                count = zone_data["zone"].current_count
                self.redis.hset("zone_occupancy", zone_name, count)

            # 6. Annotated frame for CCTV wall
            annotated = self.heatmap_annotator.annotate(scene=frame.copy(), detections=detections)
            annotated = self.box_annotator.annotate(scene=annotated, detections=detections)
            annotated = self.trace_annotator.annotate(scene=annotated, detections=detections)

            frame_count += 1

    def classify_activity(self, zone_type, keypoints_49):
        # MVP: zone-based + basic hand position heuristic from 49 keypoints
        # Keypoints 0-16: body (COCO 17)
        # Keypoints 17-22: feet (6)
        # Keypoints 23-48: hands (26, 13 per hand)

        # Hand keypoints relative to shoulder → typing, gesturing, idle
        left_wrist = keypoints_49[9]   # body left wrist
        right_wrist = keypoints_49[10] # body right wrist
        left_shoulder = keypoints_49[5]
        right_shoulder = keypoints_49[6]

        hands_forward = (left_wrist[1] > left_shoulder[1] and
                        right_wrist[1] > right_shoulder[1])  # wrists below shoulders = hands forward/on table

        zone_activity_map = {
            "coding": "coding" if hands_forward else "idle",
            "mentoring": "mentoring",
            "presenting": "presenting",
            "networking": "networking",
            "sponsor": "sponsor_engagement",
            "food": "eating",
            "rest": "resting"
        }
        return zone_activity_map.get(zone_type, "idle")
```

### 5.2 Scoring Engine

```python
# Pseudocode for scoring_worker.py

class ScoringEngine:
    def __init__(self):
        self.redis = Redis()
        self.db = AsyncSession()
        self.weights = self.load_weights()  # from scoring_config table
        self.buffer = defaultdict(list)  # participant_id → [events]
        self.flush_interval = 60  # calculate scores every 60 seconds

    async def run(self):
        last_flush = time.time()
        while True:
            # Read from Redis Stream
            events = self.redis.xread({"activity_stream": "$"}, block=1000, count=100)
            for event in events:
                self.buffer[event["participant_id"]].append(event)

            # Flush and calculate every 60 seconds
            if time.time() - last_flush >= self.flush_interval:
                await self.flush_scores()
                last_flush = time.time()

    async def flush_scores(self):
        for participant_id, events in self.buffer.items():
            # Group events by activity
            activity_durations = defaultdict(float)
            for event in events:
                activity_durations[event["activity"]] += (self.flush_interval / len(events))

            # Calculate points
            period_score = 0
            for activity, minutes in activity_durations.items():
                weight = self.weights.get(activity, 0)
                min_dwell = self.weights[activity].get("min_dwell_seconds", 120)
                if minutes * 60 >= min_dwell:
                    period_score += minutes * weight

            # Update PostgreSQL
            await self.db.execute(
                update(scores)
                .where(scores.c.participant_id == participant_id)
                .values(
                    total_score=scores.c.total_score + period_score,
                    coding_minutes=scores.c.coding_minutes + activity_durations.get("coding", 0),
                    # ... other activity minutes ...
                    last_zone=events[-1]["zone_id"],
                    last_activity=events[-1]["activity"],
                    last_seen_at=events[-1]["timestamp"],
                    updated_at=func.now()
                )
            )

            # Update Redis leaderboard
            new_total = await self.get_total_score(participant_id)
            self.redis.zadd("leaderboard", {participant_id: new_total})

            # Update Redis participant state
            self.redis.hset(f"participant:{participant_id}", mapping={
                "zone": events[-1]["zone_id"],
                "activity": events[-1]["activity"],
                "score": new_total,
                "last_seen": events[-1]["timestamp"]
            })

            # Recalculate tags
            tags = await self.calculate_tags(participant_id)
            await self.db.execute(
                update(scores).where(...).values(tags=tags)
            )

            # Write activity logs (batch insert)
            await self.db.execute(
                insert(activity_logs).values([
                    {**e, "id": None} for e in events
                ])
            )

        self.buffer.clear()
        await self.db.commit()

        # Push WebSocket updates
        await self.push_leaderboard_update()
```

### 5.3 Alert Engine

```python
class AlertEngine:
    """Runs inside heatmap_worker, checks conditions every snapshot."""

    RULES = [
        {
            "condition": lambda zones: any(z.occupancy / z.capacity > 0.9 for z in zones),
            "severity": "warning",
            "message": lambda z: f"{z.name} at {int(z.occupancy/z.capacity*100)}% capacity",
            "cooldown": 600  # don't repeat for 10 min
        },
        {
            "condition": lambda zones: any(
                z.zone_type == "mentoring" and z.occupancy == 0
                and z.empty_since > 1800 for z in zones
            ),
            "severity": "warning",
            "message": lambda z: f"Mentor booth empty for {z.empty_since//60} min"
        },
        {
            "condition": lambda metrics: metrics.energy_level < 0.3,
            "severity": "info",
            "message": "Energy dipping — consider sending food or making an announcement"
        },
        {
            "condition": lambda metrics: metrics.hours_since_food > 3,
            "severity": "info",
            "message": lambda m: f"No food sent in {m.hours_since_food} hours"
        }
    ]
```

---

## 6. DATABASE & STORAGE

### 6.1 PostgreSQL Configuration

```
# postgresql.conf optimizations for our workload

# Connection
max_connections = 50           # We have few services, not web-scale
shared_buffers = 4GB           # 25% of 16GB RAM
effective_cache_size = 12GB    # 75% of RAM

# Write-heavy workload (activity_logs inserts)
wal_level = replica
max_wal_size = 2GB
min_wal_size = 1GB
checkpoint_timeout = 10min
synchronous_commit = off       # OK to lose last ~1s of activity logs on crash

# Partitioning
# activity_logs partitioned by hour — each partition ~10K-50K rows
# Old partitions can be detached and archived post-event

# Autovacuum (important for high-insert tables)
autovacuum_vacuum_threshold = 1000
autovacuum_analyze_threshold = 500
autovacuum_vacuum_scale_factor = 0.05
```

### 6.2 Table Partitioning Strategy

```sql
-- Activity logs: hourly partitions (created before event)
-- For a 12-hour hackathon (6PM to 6AM):
CREATE TABLE activity_logs_h18 PARTITION OF activity_logs
  FOR VALUES FROM ('2026-07-15 18:00:00') TO ('2026-07-15 19:00:00');
CREATE TABLE activity_logs_h19 PARTITION OF activity_logs
  FOR VALUES FROM ('2026-07-15 19:00:00') TO ('2026-07-15 20:00:00');
-- ... through h06 next day

-- Trajectory table: same hourly partitioning
-- Heatmap snapshots: no partitioning needed (small table)
```

### 6.3 Redis Memory Layout

```
Total budget: 2GB max

Sorted Sets:
  leaderboard                    ~50KB (500 participants × 100 bytes)

Hashes:
  participant:{id} × 500         ~500KB (1KB per participant)
  zone_occupancy                 ~1KB

Strings:
  heatmap:current                ~100KB (serialized grid)
  metrics:*                      ~1KB

Streams:
  activity_stream                ~50MB (rolling window, trimmed to last 10K events)
  XTRIM activity_stream MAXLEN 10000

Total estimated: ~55MB — well within 2GB budget
```

### 6.4 FAISS Index

```
Type: IndexFlatIP (inner product on L2-normalized vectors = cosine similarity)
Dimensions: 512
Max entries: 1000 (can handle 10K+ easily)
Memory: ~2MB for 1000 vectors
Disk: faiss_index.bin (~2MB)
Lookup time: <1ms for 1000 entries (no approximate search needed at this scale)
Persistence: saved to disk every 10 registrations and on shutdown
Thread safety: FAISS is not thread-safe for writes. Single-writer pattern:
  - Registration process is the only writer (adds new embeddings)
  - Camera workers are read-only (search only)
  - Shared via memory-mapped file or in shared memory
```

### 6.5 File Storage

```
/data/
├── faces/              # Registration photos (JPEG, ~100KB each)
│   ├── P-0001.jpg
│   └── ...
├── faiss/              # FAISS index
│   ├── faiss_index.bin
│   └── embedding_map.json
├── venue/              # Venue assets
│   └── floor_plan.png
├── exports/            # Generated exports (CSV, PDF)
│   ├── trajectories_2026-07-15.csv
│   └── sponsor_lovable_report.pdf
└── backups/            # Periodic snapshots
    ├── pg_dump_2026-07-15_22-00.sql.gz
    └── redis_2026-07-15_22-00.rdb
```

---

## 7. AUTHENTICATION & PERMISSIONS

### 7.1 Auth Architecture

```
Auth Type: JWT (JSON Web Tokens)
Token lifetime: 24 hours (covers full hackathon duration)
Refresh: No refresh tokens — single long-lived token per session
Storage: httpOnly cookie (dashboard) or Authorization header (API)
Password hashing: bcrypt with salt rounds = 12
```

### 7.2 User Roles

| Role | Permissions | Users |
|------|------------|-------|
| `admin` | Full access: all endpoints, settings, scoring config, camera management, user management, data export, delete participants | Bhargavi + co-organizer (2-3 people) |
| `operator` | Read access to command center, leaderboard, participant lookup, live tracking. Can register participants. Cannot change settings or scoring weights. | Registration desk staff, volunteer coordinators (5-10 people) |
| `viewer` | Read-only access to command center and leaderboard. No participant lookup (PII protection). No settings. | Sponsors viewing their own report (if granted temporary access) |

### 7.3 Auth Flow

```
1. Pre-event: Admin creates accounts via CLI
   python manage.py create-user --username bhargavi --role admin
   python manage.py create-user --username volunteer1 --role operator

2. Login:
   POST /api/v1/auth/login
   Body: {"username": "bhargavi", "password": "..."}
   Response: {"token": "eyJ...", "role": "admin", "expires_at": "..."}
   Set-Cookie: token=eyJ...; HttpOnly; Secure; SameSite=Strict

3. All subsequent requests:
   Authorization: Bearer eyJ...
   OR cookie-based (dashboard)

4. Token validation middleware on every request:
   - Decode JWT
   - Check expiry
   - Check role permissions for endpoint
   - Return 401 (invalid/expired) or 403 (insufficient role)
```

### 7.4 Endpoint Permission Matrix

```
                                    admin   operator   viewer
POST   /register                     yes      yes       no
GET    /participants                  yes      yes       no
GET    /participants/{id}             yes      yes       no
DELETE /participants/{id}             yes      no        no
GET    /scores/leaderboard            yes      yes       yes
GET    /scores/{id}                   yes      yes       no
GET    /tracking/*                    yes      yes       no
GET    /analytics/*                   yes      yes       yes
GET    /sponsors/{id}/report          yes      yes       yes (own)
PUT    /config/scoring                yes      no        no
POST   /cameras                       yes      no        no
GET    /export/*                      yes      no        no
POST   /auth/create-user             yes      no        no
ws://  all channels                   yes      yes       yes (limited)
```

---

## 8. HOSTING & CLOUD INFRASTRUCTURE

### 8.1 Primary: Google Cloud Platform (Single GPU VM)

```
VM: Compute Engine g2-standard-8
  - 1x NVIDIA L4 GPU (24GB VRAM)
  - 8 vCPU
  - 32GB RAM
  - 200GB SSD (pd-ssd)
  - Region: us-central1-a
  - OS: Ubuntu 24.04 LTS
  - NVIDIA Driver 550+ with CUDA 12.x
  - Docker + NVIDIA Container Toolkit

Cost: ~$1.40/hr × 24 hours = ~$34 for the event
Dev/testing: shut down VM when not testing to save costs

Networking:
  - Public IP for dashboard access + RTMP ingestion
  - Firewall rules:
    - ALLOW: 0.0.0.0/0 → port 1935 (RTMP from venue)
    - ALLOW: 0.0.0.0/0 → port 3000 (dashboard, behind auth)
    - ALLOW: 0.0.0.0/0 → port 8000 (API, behind auth)
    - ALLOW: your-ip → port 22 (SSH)
    - DENY: all other inbound

Venue side:
  - Organizer laptop running ffmpeg (relays camera RTSP → RTMP to VM)
  - No GPU, no server, no special hardware
  - Decent internet required (~60 Mbps upload for 12-13 cameras)
```

### 8.2 All Services on One VM (Docker Compose)

```
Everything runs in Docker containers on the single GCE VM:
  - camera-worker × 10-13 (one per camera, GPU access)
  - scoring-engine × 1
  - heatmap-worker × 1
  - api-server × 1 (FastAPI, 4 uvicorn workers)
  - dashboard × 1 (React + nginx)
  - mediamtx × 1 (RTMP receiver)
  - postgres × 1 (PostgreSQL 16)
  - redis × 1 (Redis 7)

No external managed services during the event.
Cloud Storage used only for periodic backups (every 2 hours).
```

### 8.3 Backup Storage

```
Google Cloud Storage bucket: gs://spatialscore-data/
  - models/ (backup copy of ONNX/PT model files)
  - backups/ (pg_dump every 2 hours, FAISS index snapshots)
  - exports/ (post-event: scores CSV, trajectories CSV, sponsor PDFs)
  
Cost: <$1 total
```

---

## 9. CI/CD & VERSION CONTROL

### 9.1 Repository Structure

```
Monorepo: github.com/weeklyweights-a11y/spatialscore

Branching:
  main         — production-ready, deploys to venue hardware
  develop      — integration branch
  feature/*    — feature branches (feature/scoring-engine, feature/heatmap-viz)
  hotfix/*     — urgent fixes during event

Commit convention: Conventional Commits
  feat: add sponsor report PDF export
  fix: camera worker reconnect on RTSP timeout
  perf: batch FAISS queries for multi-face frames
  docs: update runbook for venue setup
```

### 9.2 CI Pipeline (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ruff
      - run: ruff check backend/
      - run: cd dashboard && npm run lint

  test-backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env: { POSTGRES_DB: test, POSTGRES_PASSWORD: test }
      redis:
        image: redis:7-alpine
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r backend/requirements.txt
      - run: pytest backend/tests/ -v --cov=backend --cov-report=xml

  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd dashboard && npm ci && npm test

  build-docker:
    runs-on: ubuntu-latest
    needs: [lint, test-backend, test-frontend]
    steps:
      - uses: actions/checkout@v4
      - run: docker compose -f docker-compose.yml build
      - run: docker compose -f docker-compose.yml up -d
      - run: sleep 10 && curl -f http://localhost:8000/health || exit 1
```

### 9.3 CD / Deployment

```
Pre-event deployment to venue hardware:

1. SSH into GPU machine at venue
2. git pull origin main
3. docker compose pull
4. docker compose down
5. docker compose up -d
6. Run smoke tests: python scripts/smoke_test.py
7. Verify camera streams: python scripts/test_cameras.py

No CI/CD pipeline to venue — manual deployment via SSH.
Reason: venue hardware is not internet-exposed during event.
```

---

## 10. SECURITY

### 10.1 Network Security

```
Camera VLAN:
  - Isolated from management VLAN (no cross-traffic)
  - Camera default passwords CHANGED before event
  - RTSP authentication enabled on all cameras
  - No internet access from camera VLAN

Management VLAN:
  - WPA3 WiFi with strong PSK for organizer devices
  - MAC filtering (optional, for extra lockdown)
  - Dashboard accessible only on this VLAN

Firewall rules (iptables on GPU machine):
  - ALLOW: 10.0.1.0/24 → GPU:554 (RTSP)
  - ALLOW: 10.0.2.0/24 → GPU:8000 (API)
  - ALLOW: 10.0.2.0/24 → GPU:3000 (Dashboard)
  - DENY: all other inbound
  - ALLOW: GPU → 10.0.1.0/24:554 (RTSP to cameras)
  - DENY: GPU → internet (during event, optional)
```

### 10.2 Application Security

```
Authentication:
  - JWT with HS256 signing (secret rotated per event)
  - bcrypt password hashing (12 rounds)
  - No default passwords — all created via CLI pre-event

Input validation:
  - Pydantic models on all API inputs
  - File upload: accept only JPEG/PNG, max 5MB, validate magic bytes
  - SQL injection: prevented by SQLAlchemy parameterized queries
  - XSS: React auto-escapes, CSP headers on dashboard

CORS:
  - Allowed origins: http://10.0.2.100:3000 (dashboard only)
  - No wildcard origins

Headers (set by FastAPI middleware):
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - Strict-Transport-Security: max-age=31536000 (if HTTPS)
  - Content-Security-Policy: default-src 'self'; img-src 'self' blob:; connect-src 'self' ws://10.0.2.100:8000
```

### 10.3 Data Security

```
Face embeddings:
  - Stored as 512-dim float vectors — NOT reversible to face images
  - FAISS index file encrypted at rest (LUKS on data partition)

Registration photos:
  - Stored only during event for fallback identification
  - Deleted 48 hours post-event (automated cron job)

Activity logs:
  - Anonymized 30 days post-event (participant_id → SHA256 hash)

Database:
  - PostgreSQL password auth (not trust)
  - Database not exposed outside container network

Redis:
  - requirepass enabled
  - Not exposed outside container network

Backups:
  - Encrypted with gpg before storage
  - Backup encryption key stored separately from data
```

---

## 11. RATE LIMITING

### 11.1 API Rate Limits

```python
# FastAPI middleware using slowapi

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Global: 100 requests/minute per IP
@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    # Applied globally

# Per-endpoint overrides:
@app.get("/api/v1/scores/leaderboard")
@limiter.limit("30/minute")      # Leaderboard: 30/min (updates every 30s anyway)

@app.post("/api/v1/register")
@limiter.limit("10/minute")      # Registration: 10/min (physical bottleneck is slower)

@app.get("/api/v1/export/trajectories")
@limiter.limit("5/minute")       # Export: 5/min (expensive query)

@app.put("/api/v1/config/scoring")
@limiter.limit("2/minute")       # Config changes: 2/min (prevent accidental rapid changes)
```

### 11.2 Internal Rate Limits

```
Camera worker → Redis Stream:
  Max 10 events/second per camera (10 FPS processing)
  If Redis Stream exceeds 10,000 entries, XTRIM oldest

Scoring engine → PostgreSQL:
  Batch inserts: max 1000 rows per INSERT
  Score updates: max 500 participants per flush cycle

WebSocket pushes:
  Leaderboard: max 1 push per 30 seconds
  Heatmap: max 1 push per 10 seconds
  Tracking: max 1 push per 1 second per camera
```

---

## 12. CACHING & CDN

### 12.1 Caching Strategy

```
Layer 1: Redis (hot data, real-time state)
  leaderboard         → Redis sorted set (updated every 60s by scoring engine)
  participant:{id}    → Redis hash (updated on every activity event)
  zone_occupancy      → Redis hash (updated every frame by camera workers)
  heatmap:current     → Redis string (updated every 10s by heatmap worker)
  TTL: none (actively managed, not expired)

Layer 2: API response cache (react-query on frontend)
  Leaderboard page    → staleTime: 30s, refetchInterval: 30s
  Participant detail  → staleTime: 10s (individual lookup is near-real-time)
  Analytics charts    → staleTime: 60s
  Camera list         → staleTime: 300s (rarely changes)
  Scoring config      → staleTime: 600s

Layer 3: Computed aggregates (materialized in PostgreSQL)
  sponsor_engagement  → Materialized by scoring engine every 5 minutes
  heatmap_snapshots   → Written by heatmap worker every 5 minutes
  No need for explicit cache invalidation — data is append-only during event

No CDN needed:
  - Dashboard is served on local network
  - All assets are local (no external image/font CDN)
  - Static assets served by nginx from dashboard container
  - Vendor JS/CSS bundled at build time (no external CDN dependencies)
```

### 12.2 Cache Invalidation

```
Scenario: Organizer changes scoring weights mid-event

1. PUT /api/v1/config/scoring → updates scoring_config table
2. Scoring engine reloads weights from DB (checks every flush cycle)
3. Recalculation triggered for all participants (background task)
4. New scores written to Redis leaderboard
5. WebSocket pushes updated leaderboard to all connected dashboards
6. react-query invalidation: queryClient.invalidateQueries(['leaderboard'])

Time to reflect: ~60 seconds (next scoring flush cycle)
```

---

## 13. ERROR TRACKING & LOGGING

### 13.1 Logging Architecture

```
Library: loguru (Python), structured JSON logs
Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

Format:
{
  "timestamp": "2026-07-15T02:34:12.456Z",
  "level": "ERROR",
  "service": "camera-worker-03",
  "message": "RTSP stream timeout",
  "camera_id": "CAM-03",
  "rtsp_url": "rtsp://10.0.1.13/stream",
  "retry_count": 3,
  "traceback": "..."
}
```

### 13.2 Log Destinations

```
Development:
  stdout (console) — all levels

Production (during event):
  stdout → Docker logs → journald
  File: /var/log/spatialscore/{service}.log — rotated daily, max 1GB
  Error aggregation: local SQLite error_log.db (lightweight, no external dependency)

Post-event:
  Logs collected and archived to S3 for debugging
```

### 13.3 Structured Log Events

```python
# Camera worker events
logger.info("Frame processed", camera_id="CAM-03", fps=9.8, faces_detected=3, persons_tracked=12)
logger.warning("Face match low confidence", participant="P-0042", similarity=0.52, threshold=0.5)
logger.error("RTSP stream lost", camera_id="CAM-03", retry_count=3)
logger.info("RTSP reconnected", camera_id="CAM-03", downtime_seconds=4.2)

# Scoring engine events
logger.info("Scores flushed", participants_updated=187, total_events=1240, flush_time_ms=45)
logger.warning("Scoring lag detected", lag_seconds=12, expected_interval=60)

# API events
logger.info("Registration", participant_id="P-0188", name="Riya", team="Alpha")
logger.warning("Duplicate face detected", similarity=0.92, existing="P-0042")
logger.error("Database connection lost", retry_count=1)

# System events
logger.critical("GPU memory exceeded", vram_used_mb=23500, vram_total_mb=24000)
logger.warning("Redis memory high", used_mb=1800, max_mb=2000)
```

### 13.4 Error Classification

| Severity | Action | Example |
|----------|--------|---------|
| CRITICAL | Page organizer immediately, system may be down | GPU OOM, PostgreSQL crash, all cameras offline |
| ERROR | Log + alert, auto-retry, manual check within 30 min | Single camera offline, FAISS index corrupt, scoring engine crash |
| WARNING | Log, monitor trend, check if pattern escalates | Low face match confidence, Redis memory >75%, slow query >500ms |
| INFO | Normal operation logging | Frame processed, score updated, participant registered |

---

## 14. MONITORING & ALERTS

### 14.1 Health Checks

```python
# FastAPI health endpoint

@app.get("/health")
async def health_check():
    checks = {
        "postgres": await check_postgres(),    # SELECT 1
        "redis": await check_redis(),          # PING
        "faiss_index": check_faiss_loaded(),   # index.ntotal > 0
        "cameras": {
            cam_id: check_camera_alive(cam_id)  # last frame < 30s ago
            for cam_id in camera_ids
        },
        "scoring_engine": check_scoring_alive(), # last flush < 120s ago
        "disk_space": check_disk_space(),       # >10% free
        "gpu_memory": check_gpu_memory(),       # <90% used
    }

    status = "healthy" if all_passing(checks) else "degraded"
    return {"status": status, "checks": checks, "uptime": get_uptime()}
```

### 14.2 Metrics Collection

```
Metrics stored in Redis (lightweight, no Prometheus needed for single-machine):

System metrics (collected every 30s):
  metrics:cpu_percent          — system CPU usage
  metrics:ram_used_mb          — system RAM usage
  metrics:gpu_util_percent     — GPU utilization (nvidia-smi)
  metrics:gpu_vram_used_mb     — GPU VRAM usage
  metrics:disk_free_gb         — free disk space

Application metrics (collected per flush cycle):
  metrics:total_registered     — total participants registered
  metrics:total_active         — currently tracked participants
  metrics:total_events         — activity events processed (cumulative)
  metrics:scoring_lag_seconds  — time since last score flush
  metrics:camera:{id}:fps      — actual FPS per camera
  metrics:camera:{id}:status   — up/down per camera
  metrics:api_requests_total   — total API requests served
  metrics:ws_connections       — active WebSocket connections
```

### 14.3 Alert Rules

```python
ALERT_RULES = [
    # Infrastructure alerts
    {
        "name": "gpu_memory_high",
        "condition": lambda m: m["gpu_vram_used_mb"] / m["gpu_vram_total_mb"] > 0.9,
        "severity": "critical",
        "message": "GPU memory at {pct}% — risk of OOM crash",
        "cooldown": 300
    },
    {
        "name": "disk_space_low",
        "condition": lambda m: m["disk_free_gb"] < 10,
        "severity": "critical",
        "message": "Only {gb}GB disk space remaining",
        "cooldown": 600
    },
    {
        "name": "camera_offline",
        "condition": lambda m: any(c["status"] == "down" for c in m["cameras"]),
        "severity": "error",
        "message": "Camera {cam_id} is offline",
        "cooldown": 120
    },
    {
        "name": "scoring_stale",
        "condition": lambda m: m["scoring_lag_seconds"] > 180,
        "severity": "error",
        "message": "Scoring engine hasn't flushed in {lag}s — may be crashed",
        "cooldown": 300
    },

    # Operational alerts (pushed to organizer dashboard)
    {
        "name": "zone_capacity",
        "condition": lambda z: z.occupancy / z.capacity > 0.9,
        "severity": "warning",
        "message": "{zone_name} at {pct}% capacity"
    },
    {
        "name": "mentor_booth_empty",
        "condition": lambda z: z.zone_type == "mentoring" and z.occupancy == 0 and z.empty_minutes > 30,
        "severity": "warning",
        "message": "Mentor booth empty for {min} minutes"
    },
    {
        "name": "energy_dip",
        "condition": lambda m: m["energy_level"] < 0.25,
        "severity": "info",
        "message": "Event energy is low — consider an announcement or food drop"
    }
]
```

### 14.4 Alert Delivery

```
During event:
  1. Dashboard alert feed (WebSocket push) — always active
  2. Sound notification on organizer laptop (browser notification API)

If internet available:
  3. Slack webhook to #spatialscore-alerts channel
  4. SMS via Twilio to organizer phone (critical only)

Post-event:
  5. Alert log exported as CSV for event retrospective
```

---

## 15. TESTING STRATEGY

### 15.1 Test Pyramid

```
                    ┌─────────┐
                    │ E2E (5) │  — Full system with simulated cameras
                   ┌┴─────────┴┐
                   │ Integ (20)│  — Service-to-service (API→DB, Worker→Redis)
                  ┌┴───────────┴┐
                  │  Unit (100+) │  — Individual functions, classifiers, scorers
                  └──────────────┘
```

### 15.2 Unit Tests

```python
# tests/unit/test_zone_classifier.py
def test_point_in_polygon():
    zone = Zone(polygon=[(0,0), (10,0), (10,10), (0,10)])
    assert classify_zone((5, 5), [zone]) == zone
    assert classify_zone((15, 15), [zone]) is None

# tests/unit/test_scoring.py
def test_coding_score():
    events = [{"activity": "coding"}] * 60  # 60 events in 60 seconds
    score = calculate_period_score(events, weights={"coding": 1.0})
    assert score == 1.0  # 1 minute × 1.0 weight

def test_mentoring_weight():
    events = [{"activity": "mentoring"}] * 60
    score = calculate_period_score(events, weights={"mentoring": 2.0})
    assert score == 2.0  # 1 minute × 2.0 weight

def test_idle_zero_score():
    events = [{"activity": "idle"}] * 60
    score = calculate_period_score(events, weights={"idle": 0})
    assert score == 0

# tests/unit/test_tags.py
def test_builder_tag():
    minutes = {"coding": 360, "collaborating": 60, "mentoring": 30, "networking": 30}
    tags = calculate_tags(minutes)
    assert "Builder" in tags  # coding > 50% of total

def test_mentor_tag():
    minutes = {"coding": 200, "mentoring": 120, "collaborating": 60}
    tags = calculate_tags(minutes)
    assert "Mentor" in tags  # mentoring > 15% of total

# tests/unit/test_face_matching.py
def test_known_face_match():
    index = build_test_index(embeddings=[known_embedding])
    result = search(index, known_embedding)
    assert result.similarity > 0.5

def test_unknown_face_rejected():
    index = build_test_index(embeddings=[known_embedding])
    result = search(index, random_embedding)
    assert result.similarity < 0.3
```

### 15.3 Integration Tests

```python
# tests/integration/test_api.py
async def test_registration_flow(client, db):
    # Register a participant
    response = await client.post("/api/v1/register", files={"photo": face_image}, data={...})
    assert response.status_code == 201
    pid = response.json()["participant_id"]

    # Verify in database
    participant = await db.get(Participant, pid)
    assert participant.name == "Test User"

    # Verify FAISS index updated
    response = await client.get(f"/api/v1/participants/{pid}")
    assert response.json()["name"] == "Test User"

# tests/integration/test_scoring_pipeline.py
async def test_activity_to_score(redis, db):
    # Simulate camera worker emitting events
    for _ in range(60):
        redis.xadd("activity_stream", {"participant_id": pid, "activity": "coding", ...})

    # Run scoring flush
    await scoring_engine.flush_scores()

    # Verify score updated
    score = await db.get(Score, pid)
    assert score.total_score > 0
    assert score.coding_minutes > 0

# tests/integration/test_websocket.py
async def test_leaderboard_ws(client):
    async with client.websocket_connect("/ws/leaderboard?token=...") as ws:
        data = await asyncio.wait_for(ws.receive_json(), timeout=35)
        assert data["type"] == "leaderboard"
        assert len(data["data"]) > 0
```

### 15.4 End-to-End Tests

```python
# tests/e2e/test_full_pipeline.py

def test_full_pipeline():
    """
    Simulates the entire system with fake video streams.
    1. Start all services via docker compose
    2. Create fake RTSP streams (pre-recorded video loops)
    3. Register 10 test participants with known faces
    4. Let system run for 5 minutes
    5. Verify: all 10 participants have scores > 0
    6. Verify: heatmap shows non-zero occupancy
    7. Verify: leaderboard WebSocket emits data
    8. Verify: participant lookup returns activity timeline
    """
```

### 15.5 Load Testing

```python
# scripts/simulate_streams.py
"""
Generates N fake RTSP streams from pre-recorded video.
Each stream loops a video file with known faces.
Used for:
  - Load testing camera workers (4, 6, 8, 12 streams)
  - Verifying scoring accuracy (known faces → expected scores)
  - Measuring latency (frame capture to score update)
  - GPU VRAM usage under load
"""
```

### 15.6 Pre-Event Dry Run Checklist

```
□ All cameras streaming and detected by system
□ Registration: enroll 5 test participants, verify face matching
□ Walk through each zone — verify zone classification
□ Check leaderboard updates in <60 seconds
□ Check heatmap updates in <10 seconds
□ Verify alert fires when zone is "full" (simulate)
□ Run for 2 hours continuously — no memory leaks
□ Simulate camera disconnect + reconnect
□ Simulate scoring engine crash + auto-restart
□ Test PDF export for sponsor report
□ Verify backup/restore works
```

---

## 16. SCALING STRATEGY

### 16.1 Scaling Dimensions

| Dimension | Current (MVP) | Scale Target | How |
|-----------|--------------|-------------|-----|
| Cameras | 4-6 | 20+ | Add GPU (second RTX 4090) or distribute workers across machines |
| Participants | 200 | 2000 | FAISS handles 10K+ vectors easily. PostgreSQL partitioning handles write volume |
| Events/second | ~40-60 | 500+ | Redis Streams handle 100K+ writes/second. Batch inserts to PostgreSQL |
| Dashboard users | 5-10 | 50 | FastAPI with 4 uvicorn workers handles 50 concurrent WebSocket connections |
| Events per year | 1 | 50+ | Multi-tenant architecture in Phase 3 (event_id in all tables) |

### 16.2 Vertical Scaling (Same Machine)

```
Current: 1× RTX 4090 (24GB VRAM)
  → Handles 8-15 cameras at 10 FPS

Upgrade: 2× RTX 4090 or 1× A6000 (48GB)
  → Handles 20-30 cameras
  → Camera workers distributed across GPUs: CUDA_VISIBLE_DEVICES=0 vs =1

Memory: 32GB → 64GB → 128GB RAM
  → More room for PostgreSQL shared_buffers and Redis
  → More camera worker processes

CPU: 16-core → 32-core
  → More camera worker processes (1 per core)
```

### 16.3 Horizontal Scaling (Multiple Machines)

```
Phase 3 architecture for multi-venue or large events:

Machine 1 (GPU): Camera workers only
  → All SCRFD + ArcFace + YOLO inference
  → Writes to central Redis

Machine 2 (CPU): API + Scoring + Dashboard
  → FastAPI server
  → Scoring engine consuming Redis Stream
  → PostgreSQL + Redis

Machine 3 (GPU, optional): Additional cameras
  → Same camera worker containers
  → Connects to same central Redis

Communication: Redis Streams over network
  → Camera workers XADD to central Redis
  → Scoring engine XREAD from central Redis
```

### 16.4 Database Scaling Path

```
200 participants, 12 hours, 10 FPS across 4 cameras:
  → ~1.7M activity log rows (manageable in single PostgreSQL instance)

2000 participants, 24 hours, 10 FPS across 20 cameras:
  → ~172M rows → partition aggressively, archive old partitions, consider TimescaleDB

If write throughput becomes bottleneck:
  → Switch to TimescaleDB (PostgreSQL extension for time-series)
  → OR write activity logs to ClickHouse (columnar, handles 1M+ inserts/second)
  → Keep PostgreSQL for participant profiles and scores (low write volume)
```

---

## 17. DISASTER RECOVERY & BACKUP

### 17.1 Backup Strategy

```
During event (automated):
  PostgreSQL: pg_dump every 2 hours → /data/backups/pg_dump_{timestamp}.sql.gz
  Redis: RDB snapshot every 2 hours + AOF for every write
  FAISS index: saved to disk every 10 registrations + on shutdown

Retention:
  Keep all backups from current event
  Delete backups from previous events after 30 days (unless data export requested)
```

### 17.2 Recovery Scenarios

```
Scenario: Camera worker crashes
  Impact: One camera stops tracking
  Recovery: Docker auto-restarts container (restart: always)
  Time: ~5 seconds
  Data loss: 0-5 seconds of tracking for that camera

Scenario: Scoring engine crashes
  Impact: Scores stop updating
  Recovery: Docker auto-restarts. Engine resumes consuming Redis Stream from last ACK.
  Time: ~10 seconds
  Data loss: None (unprocessed events remain in Redis Stream)

Scenario: PostgreSQL crashes
  Impact: Score writes fail, API queries fail
  Recovery: Docker auto-restarts PostgreSQL. WAL-based recovery.
  Time: ~30 seconds
  Data loss: <1 second (synchronous_commit=off means last ~1s of writes may be lost)
  Mitigation: Redis has current state — API falls back to Redis during DB recovery

Scenario: Redis crashes
  Impact: Real-time state lost, WebSocket updates stop
  Recovery: Docker auto-restarts. AOF replay recovers state.
  Time: ~10 seconds
  Data loss: Last ~1 second of state (AOF appendfsync=everysec)

Scenario: GPU machine power failure
  Impact: Everything stops
  Recovery: UPS provides 10-15 min to graceful shutdown. On power restore, docker compose up.
  Time: 2-5 minutes
  Data loss: PostgreSQL WAL + Redis AOF recover to within seconds of failure.

Scenario: GPU hardware failure (total loss)
  Impact: System is down for rest of event
  Recovery: Fail over to cloud GPU (pre-configured AWS g5.2xlarge AMI)
  Time: 15-30 minutes (spin up cloud, VPN cameras, restore from backup)
  Prerequisite: Latest backup synced to S3 every 2 hours
```

---

## 18. PERFORMANCE BUDGETS

### 18.1 Latency Budgets

| Path | Budget | Measured |
|------|--------|---------|
| Frame capture → activity event in Redis | <100ms | Camera worker loop |
| Activity event → score update | <60s | Scoring engine flush interval |
| Score update → dashboard display | <5s | WebSocket push + render |
| End-to-end: physical action → dashboard | <65s | Full pipeline |
| API response: leaderboard | <200ms | 95th percentile |
| API response: participant lookup | <300ms | 95th percentile (includes timeline query) |
| API response: registration | <2s | Includes face detection + embedding + FAISS add |
| WebSocket: initial connection | <500ms | Including auth |

### 18.2 Throughput Budgets

| Metric | Budget |
|--------|--------|
| Frames processed per second (all cameras) | 40-60 FPS total (4-6 cameras × 10 FPS) |
| Activity events per second | 40-60 events/s (1 per frame per camera) |
| PostgreSQL inserts per minute | ~3,600 activity log rows |
| Redis operations per second | ~200 (reads + writes + stream ops) |
| WebSocket messages per minute | ~20 (leaderboard + heatmap + alerts) |

### 18.3 Resource Budgets

| Resource | Budget | Alert Threshold |
|----------|--------|----------------|
| GPU VRAM | <4GB of 24GB | >20GB (85%) |
| System RAM | <32GB of 64GB | >56GB (88%) |
| CPU | <60% average | >85% sustained |
| Disk | <200GB of 1TB | >900GB (90%) |
| Redis memory | <500MB of 2GB | >1.5GB (75%) |

---

## 19. DATA PRIVACY & COMPLIANCE

### 19.1 Data Classification

| Data Type | Classification | Retention | Encryption |
|-----------|---------------|-----------|------------|
| Face embeddings | PII (biometric) | Deleted 48 hours post-event | At rest (LUKS) |
| Registration photos | PII | Deleted 48 hours post-event | At rest (LUKS) |
| Participant names + emails | PII | Anonymized 30 days post-event | At rest |
| Activity logs | PII (linked to participant_id) | Anonymized 30 days post-event | At rest |
| Scores | PII (linked to participant_id) | Anonymized 30 days post-event | At rest |
| Trajectories | PII (linked to participant_id) | Anonymized 30 days post-event | At rest |
| Heatmap aggregates | Non-PII (no individual data) | Retained indefinitely | None needed |
| Sponsor reports | Non-PII (aggregate only) | Retained indefinitely | None needed |

### 19.2 Consent Framework

```
Registration consent (verbal + checkbox):
  "This event uses cameras to track participant activity for event operations.
   Your location and general activity (coding, collaborating, presenting, etc.)
   will be recorded. Data is used by organizers only. You can opt out at any time
   by visiting the registration desk."

Venue signage (posted at all entrances):
  "This venue uses CCTV cameras and drones for event operations.
   Participant activity is tracked for scoring and analytics purposes.
   Data is used by event organizers only. Opt-out available at registration desk."
```

### 19.3 GDPR / CCPA Compliance

```
Right of access:
  GET /api/v1/participants/{id} returns all data about a participant
  GET /api/v1/export/participant/{id} returns downloadable JSON

Right to erasure:
  DELETE /api/v1/participants/{id}
  → Removes face embedding from FAISS
  → Anonymizes all activity logs (SHA256 hash replaces participant_id)
  → Deletes registration photo
  → Sets opted_out = true

Data minimization:
  → Raw video frames are never stored
  → Only derived data (embeddings, bounding boxes, keypoints, zone, activity) is stored
  → Face embeddings are not reversible to face images

Data processing agreement:
  → Template DPA available for venues/sponsors who receive reports
```

### 19.4 Anonymization Process

```python
# scripts/anonymize.py — run 30 days post-event

async def anonymize_event(event_id):
    # 1. Delete all face embeddings
    faiss_index.reset()
    os.remove("faiss_index.bin")

    # 2. Delete registration photos
    shutil.rmtree(f"/data/faces/{event_id}/")

    # 3. Anonymize participant records
    participants = await db.execute(select(Participant).where(event_id=event_id))
    for p in participants:
        anon_id = hashlib.sha256(p.id.encode()).hexdigest()[:16]
        await db.execute(
            update(Participant)
            .where(Participant.id == p.id)
            .values(name=f"Anon-{anon_id}", email=None, photo_path=None)
        )

    # 4. Anonymize activity logs
    await db.execute(
        text("""
            UPDATE activity_logs
            SET participant_id = encode(sha256(participant_id::text::bytea), 'hex')
            WHERE event_id = :event_id
        """),
        {"event_id": event_id}
    )

    # 5. Anonymize trajectories (same pattern)
    # 6. Anonymize scores (same pattern)

    logger.info(f"Event {event_id} anonymized successfully")
```

---

## 20. OPERATIONAL RUNBOOK

### 20.1 Pre-Event Setup (Day Before)

```
□ 1. Hardware setup
    □ Position GPU machine in secure, ventilated location
    □ Connect UPS
    □ Connect to venue network (camera VLAN + management VLAN)

□ 2. Camera installation
    □ Mount 4-6 IP cameras at 2-3m height covering all zones
    □ Connect to PoE switch
    □ Configure RTSP URLs and test streams
    □ Change default camera passwords

□ 3. Software deployment
    □ SSH into GPU machine
    □ git pull origin main
    □ docker compose up -d
    □ Run: python scripts/test_cameras.py (verify all streams)

□ 4. Venue configuration
    □ Upload floor plan: POST /api/v1/config/venue
    □ Define zones: use Zone Editor in Settings
    □ Draw polygons on each camera view
    □ Set scoring weights: use Scoring Config in Settings

□ 5. Create user accounts
    □ python manage.py create-user --username bhargavi --role admin
    □ python manage.py create-user --username volunteer1 --role operator
    □ ... for all registration desk staff

□ 6. Dry run
    □ Register 5 test participants
    □ Walk through zones, verify tracking
    □ Check leaderboard, heatmap, alerts
    □ Run for 2 hours, check for memory leaks
    □ Delete test participants
```

### 20.2 Event Day Operations

```
REGISTRATION OPEN:
  □ Staff log into registration app on tablets
  □ Verify face detection working under venue lighting
  □ Monitor registration count on command center

DURING EVENT (every 2 hours):
  □ Check command center — all cameras green
  □ Check GPU metrics (nvidia-smi or dashboard)
  □ Check disk space
  □ Verify scoring is updating (leaderboard changes)
  □ Check backup ran successfully
  □ Review any alerts

IF CAMERA GOES OFFLINE:
  1. Check physical connection (cable, power)
  2. Check camera RTSP URL: ffplay rtsp://...
  3. Camera worker should auto-reconnect (check logs)
  4. If persistent: restart camera worker container
     docker compose restart camera-worker-{N}

IF SCORING STOPS UPDATING:
  1. Check scoring engine logs: docker compose logs scoring-engine
  2. Check Redis Stream: redis-cli XLEN activity_stream
  3. Restart scoring engine: docker compose restart scoring-engine

IF SYSTEM IS SLUGGISH:
  1. Check GPU: nvidia-smi (VRAM usage, GPU utilization)
  2. Check CPU: htop (per-core usage)
  3. Check Redis: redis-cli INFO memory
  4. Check PostgreSQL: check for long-running queries
```

### 20.3 Post-Event Teardown

```
□ 1. Export data
    □ Download all scores: GET /api/v1/export/scores
    □ Download trajectory data: GET /api/v1/export/trajectories
    □ Generate sponsor reports: GET /api/v1/sponsors/{id}/report/pdf

□ 2. Backup
    □ Full pg_dump
    □ Redis RDB snapshot
    □ Copy /data/ to external drive

□ 3. Schedule anonymization
    □ Set cron job for 30 days from now: python scripts/anonymize.py

□ 4. Hardware teardown
    □ Power down GPU machine
    □ Disconnect cameras
    □ Return/store equipment
```

---

*End of System Specification — Version 1.0*
*SpatialScore for Buildathon Dallas*
