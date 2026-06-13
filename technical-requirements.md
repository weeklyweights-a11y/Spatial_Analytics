# Technical Requirements Document
# SpatialScore — Real-Time Hackathon Intelligence Platform

**Version:** 1.0
**Date:** June 2026

---

## 1. SYSTEM ARCHITECTURE OVERVIEW

```
VENUE (Dallas)                    GOOGLE CLOUD (us-central1)
───────────────                   ───────────────────────────────────────
                                   
  CCTV Cameras                     GCP VM: g2-standard-8 (NVIDIA L4)
  (10-13 across                    ┌─────────────────────────────────┐
   3 floors)                       │                                 │
      │                            │  MediaMTX (RTMP → local RTSP)  │
      │ RTSP                       │         │                      │
      ▼                            │         ▼                      │
  ┌──────────┐                     │  Camera Workers (1 per stream) │
  │ Organizer│    ffmpeg           │  ┌─────────────────────────┐   │
  │ Laptop   │──── RTMP ────────→  │  │ YOLO11-Pose (GPU)      │   │
  │ (relay)  │    over             │  │ SCRFD + ArcFace (GPU)   │   │
  └──────────┘    internet         │  │ FAISS index (RAM)       │   │
                                   │  │ sv.PolygonZone          │   │
                                   │  │ sv.ByteTrack            │   │
                                   │  └──────────┬──────────────┘   │
                                   │             │ events           │
                                   │             ▼                  │
                                   │  Redis (Docker container)      │
                                   │  ┌─────────────────────────┐   │
                                   │  │ activity_stream         │   │
                                   │  │ leaderboard             │   │
                                   │  │ participant state       │   │
                                   │  │ zone_occupancy          │   │
                                   │  └──────────┬──────────────┘   │
                                   │             │                  │
                                   │             ▼                  │
                                   │  Scoring Engine                │
                                   │             │                  │
                                   │             ▼                  │
                                   │  PostgreSQL (Docker container) │
                                   │  ┌─────────────────────────┐   │
                                   │  │ participants (1,000)    │   │
                                   │  │ scores (1,000)          │   │
                                   │  │ activity_logs (~9M rows)│   │
                                   │  │ zones, cameras, sponsors│   │
                                   │  └─────────────────────────┘   │
                                   │                                 │
                                   │  API Server (FastAPI)           │
                                   │  ┌─────────────────────────┐   │
                                   │  │ REST + WebSocket        │   │
                                   │  │ Annotated MJPEG streams │   │
                                   │  └──────────┬──────────────┘   │
                                   │             │                  │
                                   │  Dashboard (React + nginx)     │
                                   │  ┌─────────────────────────┐   │
                                   │  │ CCTV wall (camera grid) │   │
                                   │  │ Click-to-inspect cards  │   │
                                   │  │ Heatmap + Leaderboard   │   │
                                   │  └─────────────────────────┘   │
                                   │                                 │
                                   │  Cron → Cloud Storage (backups)│
                                   └─────────────────────────────────┘
                                              │
                                              ▼
                               Organizer browser (any device)
                               https://spatialscore.buildathon.co
```

---

## 2. DATABASE SCHEMA

### 2.1 PostgreSQL Tables

```sql
-- Core participant identity
CREATE TABLE participants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255),
    team_name       VARCHAR(255),
    track           VARCHAR(100),        -- e.g. "AI/ML", "Web3", "DevTools"
    skills          TEXT[],              -- e.g. {"python", "react", "ml"}
    photo_path      VARCHAR(500),        -- path to registration photo
    embedding_id    INTEGER,             -- index position in FAISS
    registered_at   TIMESTAMP DEFAULT NOW(),
    opted_out       BOOLEAN DEFAULT FALSE
);

-- Venue zone definitions
CREATE TABLE zones (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL,     -- e.g. "Coding Zone A"
    zone_type       VARCHAR(50) NOT NULL,      -- coding, mentoring, presenting, networking, sponsor, food, rest
    camera_id       VARCHAR(50) NOT NULL,      -- which camera covers this zone
    polygon_coords  JSONB NOT NULL,            -- [[x1,y1],[x2,y2],...] polygon vertices in camera frame
    floor_coords    JSONB,                     -- real-world floor coordinates for heatmap
    capacity        INTEGER,                   -- max people
    sponsor_id      UUID REFERENCES sponsors(id),  -- if zone_type = 'sponsor'
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Camera configuration
CREATE TABLE cameras (
    id              VARCHAR(50) PRIMARY KEY,   -- e.g. "CAM-01"
    name            VARCHAR(100),
    rtsp_url        VARCHAR(500) NOT NULL,
    camera_type     VARCHAR(20) NOT NULL,      -- 'cctv' or 'drone'
    position        JSONB,                     -- {x, y, z} in venue coordinates
    fov_degrees     FLOAT,
    resolution      VARCHAR(20),               -- e.g. "1920x1080"
    fps_target      INTEGER DEFAULT 10,
    is_active       BOOLEAN DEFAULT TRUE
);

-- Activity log — the core data table (high write volume)
CREATE TABLE activity_logs (
    id              BIGSERIAL PRIMARY KEY,
    participant_id  UUID NOT NULL REFERENCES participants(id),
    camera_id       VARCHAR(50) NOT NULL REFERENCES cameras(id),
    zone_id         UUID NOT NULL REFERENCES zones(id),
    activity        VARCHAR(50) NOT NULL,      -- coding, collaborating, mentoring, presenting, networking, idle, eating, helping_others
    bbox            JSONB,                     -- [x1, y1, x2, y2]
    keypoints       JSONB,                     -- 17 body landmarks
    confidence      FLOAT,                     -- detection confidence
    timestamp       TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Partition by time for query performance
    CONSTRAINT activity_logs_time_check CHECK (timestamp IS NOT NULL)
) PARTITION BY RANGE (timestamp);

-- Create hourly partitions (generated before event)
-- CREATE TABLE activity_logs_2026_07_15_18 PARTITION OF activity_logs
--   FOR VALUES FROM ('2026-07-15 18:00:00') TO ('2026-07-15 19:00:00');

-- Scores — current state per participant
CREATE TABLE scores (
    participant_id  UUID PRIMARY KEY REFERENCES participants(id),
    total_score     FLOAT DEFAULT 0,
    coding_minutes      FLOAT DEFAULT 0,
    collaborating_minutes FLOAT DEFAULT 0,
    mentoring_minutes   FLOAT DEFAULT 0,
    presenting_minutes  FLOAT DEFAULT 0,
    networking_minutes  FLOAT DEFAULT 0,
    helping_minutes     FLOAT DEFAULT 0,
    idle_minutes        FLOAT DEFAULT 0,
    tags            TEXT[],                -- ['Builder', 'Mentor', 'Night Owl']
    rank            INTEGER,
    last_zone       VARCHAR(100),
    last_activity   VARCHAR(50),
    last_seen_at    TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Scoring configuration
CREATE TABLE scoring_config (
    activity        VARCHAR(50) PRIMARY KEY,
    weight          FLOAT NOT NULL,
    min_dwell_seconds INTEGER DEFAULT 120,   -- minimum time to count
    description     TEXT
);

-- Insert default weights
INSERT INTO scoring_config (activity, weight, min_dwell_seconds, description) VALUES
    ('coding', 1.0, 120, 'Sitting in coding zone with laptop posture'),
    ('collaborating', 1.5, 120, 'Multiple people in proximity in coding zone'),
    ('mentoring', 2.0, 300, 'In mentor booth or visiting other teams'),
    ('presenting', 2.0, 60, 'On demo stage facing audience'),
    ('networking', 1.2, 120, 'In networking lounge or sponsor area'),
    ('helping_others', 1.8, 600, 'Detected in another teams coding area'),
    ('sponsor_engagement', 1.0, 120, 'Engaged at sponsor booth'),
    ('eating', 0, 0, 'In food area'),
    ('resting', 0, 0, 'In rest area'),
    ('idle', 0, 0, 'Walking without stopping');

-- Sponsors
CREATE TABLE sponsors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    tier            VARCHAR(50),               -- 'platinum', 'gold', 'silver'
    booth_zone_id   UUID REFERENCES zones(id),
    logo_url        VARCHAR(500),
    contact_email   VARCHAR(255)
);

-- Sponsor engagement aggregates (materialized from activity_logs)
CREATE TABLE sponsor_engagement (
    sponsor_id      UUID NOT NULL REFERENCES sponsors(id),
    hour_bucket     TIMESTAMP NOT NULL,
    unique_visitors INTEGER DEFAULT 0,
    total_visits    INTEGER DEFAULT 0,
    avg_dwell_seconds FLOAT DEFAULT 0,
    return_visitors INTEGER DEFAULT 0,
    PRIMARY KEY (sponsor_id, hour_bucket)
);

-- Heatmap snapshots (stored every 5 minutes)
CREATE TABLE heatmap_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMP NOT NULL,
    zone_occupancy  JSONB NOT NULL,           -- {"Coding Zone A": 34, "Mentor Booth": 2, ...}
    total_active    INTEGER,
    energy_level    FLOAT                     -- 0-1 normalized activity metric
);

-- Trajectory export (for robotics training data)
CREATE TABLE trajectories (
    id              BIGSERIAL PRIMARY KEY,
    participant_id  UUID REFERENCES participants(id),
    timestamp       TIMESTAMP NOT NULL,
    x               FLOAT NOT NULL,           -- floor coordinate
    y               FLOAT NOT NULL,           -- floor coordinate
    vx              FLOAT,                    -- velocity x
    vy              FLOAT,                    -- velocity y
    zone_id         UUID REFERENCES zones(id),
    activity        VARCHAR(50)
);

-- Indexes for query performance
CREATE INDEX idx_activity_logs_participant ON activity_logs(participant_id, timestamp);
CREATE INDEX idx_activity_logs_zone ON activity_logs(zone_id, timestamp);
CREATE INDEX idx_activity_logs_timestamp ON activity_logs(timestamp);
CREATE INDEX idx_trajectories_participant ON trajectories(participant_id, timestamp);
CREATE INDEX idx_scores_rank ON scores(total_score DESC);
```

### 2.2 Redis Data Structures

```
# Real-time leaderboard (sorted set)
ZADD leaderboard <score> <participant_id>

# Current participant state (hash per participant)
HSET participant:<id> zone "Coding Zone A"
HSET participant:<id> activity "coding"
HSET participant:<id> score 342.5
HSET participant:<id> last_seen "2026-07-15T02:34:12Z"
HSET participant:<id> camera "CAM-03"

# Zone occupancy (hash)
HSET zone_occupancy "Coding Zone A" 34
HSET zone_occupancy "Mentor Booth" 2
HSET zone_occupancy "Demo Stage" 0

# Heatmap grid (current, updated every 10s)
SET heatmap:current <serialized 2D numpy array>

# Real-time event metrics
SET metrics:total_active 187
SET metrics:energy_level 0.73
SET metrics:avg_score 245.8
```

### 2.3 FAISS Index

```
# In-memory FAISS index
# Type: IndexFlatIP (inner product = cosine similarity on normalized vectors)
# Dimensions: 512 (ArcFace embedding size)
# Entries: 1 per registered participant
# Lookup: < 1ms for 1000 entries

# Stored on disk as: faiss_index.bin
# Mapped to participant IDs via: embedding_id_to_participant_id.json
```

---

## 3. API DESIGN

### 3.1 REST Endpoints (All Auth-Protected, Organizer Only)

```
REGISTRATION
  POST   /api/register              — Register new participant (photo + profile)
  GET    /api/participants           — List all participants (with filters)
  GET    /api/participants/{id}      — Get participant profile + full score + timeline
  GET    /api/participants/search?q= — Search by name, team, or track
  DELETE /api/participants/{id}      — Remove participant (opt-out, delete embedding)

SCORES + LOOKUP
  GET    /api/scores/leaderboard     — All participants ranked by score
  GET    /api/scores/leaderboard?sort_by=mentoring — Rank by specific activity
  GET    /api/scores/{participant_id} — Detailed score breakdown + radar data
  GET    /api/scores/{participant_id}/timeline — Hour-by-hour activity breakdown
  GET    /api/scores/compare?ids=a,b,c — Side-by-side comparison for judging

LIVE TRACKING
  GET    /api/tracking/active        — All currently active participants + locations
  GET    /api/tracking/{participant_id} — Where is this person right now
  GET    /api/tracking/zone/{zone_id} — Who is in this zone right now

ZONES
  GET    /api/zones                  — List all zones with current occupancy
  POST   /api/zones                  — Create zone
  PUT    /api/zones/{id}             — Update zone polygon
  GET    /api/zones/{id}/visitors    — List participants currently in zone

ANALYTICS
  GET    /api/analytics/heatmap      — Current heatmap data
  GET    /api/analytics/energy       — Energy level over time
  GET    /api/analytics/zones        — Zone utilization over time

SPONSORS
  GET    /api/sponsors/{id}/report   — Generate sponsor engagement report
  GET    /api/sponsors/{id}/report/pdf — Download PDF report

CAMERAS
  GET    /api/cameras                — List cameras with status
  POST   /api/cameras                — Add camera
  PUT    /api/cameras/{id}/zones     — Define zones for camera

CONFIG
  GET    /api/config/scoring         — Get scoring weights
  PUT    /api/config/scoring         — Update scoring weights

EXPORT
  GET    /api/export/trajectories    — Download trajectory data (CSV)
  GET    /api/export/all-scores      — Download all participant scores (CSV)
```

### 3.2 WebSocket Channels (Auth-Protected, Organizer Only)

```
ws://server/ws/leaderboard       — Pushes updated scores every 30s
ws://server/ws/heatmap           — Pushes zone occupancy every 10s
ws://server/ws/tracking/{cam_id} — Pushes person positions for camera view
ws://server/ws/alerts            — Pushes organizer alerts (zone full, energy dip, etc.)
ws://server/ws/participant/{id}  — Pushes live updates for specific participant lookup
```

---

## 4. UI/UX DESIGN

### 4.1 Registration App (Tablet at Check-in Desk)

```
┌─────────────────────────────────────────┐
│  SPATIALSCORE — REGISTRATION            │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────────────────┐               │
│  │                     │               │
│  │   CAMERA PREVIEW    │               │
│  │   (live feed)       │               │
│  │                     │               │
│  │  [Face detected]    │               │
│  └─────────────────────┘               │
│                                         │
│  Name:    [________________]            │
│  Email:   [________________]            │
│  Team:    [________________]            │
│  Track:   [▼ Select Track  ]            │
│  Skills:  [python] [react] [+ add]      │
│                                         │
│  [x] Participant informed about camera    │
│    tracking for event operations.       │
│    Consent confirmed.                   │
│                                         │
│  [ REGISTER ]                           │
│                                         │
│  Registered: Riya Sharma                │
│     Embedding stored. Tracking active.  │
│     Total registered: 187               │
└─────────────────────────────────────────┘
```

### 4.2 CCTV Monitoring Wall — Primary Dashboard (Desktop, Auth Protected)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SPATIALSCORE — CCTV WALL                         [Bhargavi v] [Settings]    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  GROUND FLOOR              │  1ST FLOOR              │  2ND FLOOR       │
│  ┌────────────────────┐    │  ┌────────────────────┐ │ ┌──────────────┐│
│  │ CAM-01 Coding A    │    │  │ CAM-05 Coding C    │ │ │ CAM-09 Netw  ││
│  │ ┌──┐ ┌──┐ ┌──┐     │    │  │ ┌──┐ ┌──┐         │ │ │ ┌──┐ ┌──┐   ││
│  │ │Ri│ │Ar│ │De│     │    │  │ │Sa│ │Ka│         │ │ │ │Mi│ │Jo│   ││
│  │ └──┘ └──┘ └──┘     │    │  │ └──┘ └──┘         │ │ │ └──┘ └──┘   ││
│  │  34 people          │    │  │  28 people         │ │ │  18 people  ││
│  └────────────────────┘    │  └────────────────────┘ │ └──────────────┘│
│  ┌────────────────────┐    │  ┌────────────────────┐ │ ┌──────────────┐│
│  │ CAM-02 Coding B    │    │  │ CAM-06 Demo Stage  │ │ │ CAM-10 Spons ││
│  │ ┌──┐ ┌──┐          │    │  │ ┌──┐               │ │ │ ┌──┐        ││
│  │ │Ma│ │Le│          │    │  │ │Pr│ presenting    │ │ │ │Vi│ Lovable ││
│  │ └──┘ └──┘          │    │  │ └──┘               │ │ │ └──┘        ││
│  │  22 people          │    │  │  3 people          │ │ │  12 people  ││
│  └────────────────────┘    │  └────────────────────┘ │ └──────────────┘│
│                            │                          │                 │
│  ┌─────── SCORE CARD (click on any person) ─────────────────────────┐  │
│  │  ┌─────┐  Riya Sharma | Team Alpha | AI/ML Track                │  │
│  │  │photo│  Coding Zone A (CAM-01) | Collaborating                   │  │
│  │  └─────┘  Score: 918 pts | Rank: #7 of 1,000                    │  │
│  │                                                                   │  │
│  │  Coding ████░░ 33%  | Collab ███░░░ 25% | Mentor ██░░░░ 17%    │  │
│  │  Present █░░░░░  8% | Network ██░░░░ 17%                        │  │
│  │  Tags: [Builder] [Mentor] [Night Owl]                            │  │
│  │                                                     [Full Profile]│  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  HEATMAP (mini)        │ LEADERBOARD        │ ENERGY        │ ALERTS   │
│  ┌───────────────┐     │ 1. Arjun  1,204    │ ▓▓▓▓▓▓▓░ 73% │ ! Code A│
│  │ GF ████ ██░   │     │ 2. Maya   1,150    │              │   at 95% │
│  │ 1F ██░░ ████  │     │ 3. Dev    1,089    │  ╭──╮        │ ! Mentor│
│  │ 2F ░░░░ ▓▓░░  │     │ 4. Sarah  1,032    │ ╭╯  ╰╮      │   empty  │
│  └───────────────┘     │ 5. Kai      998    │╯     ╰──    │  30 min  │
│  [Expand]              │ [View All]          │              │          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Interaction flow:**
- Camera feeds show live video with labeled bounding boxes (color-coded by activity)
- Click any person's box → score card appears at bottom
- Click another person → card updates. Click empty space → card closes.
- Click [Full Profile] → opens detailed timeline view
- Click [Expand] on heatmap → full floor-plan view per floor
- Click [View All] on leaderboard → full sortable/filterable table

### 4.4 Sponsor Report View (Inside Organizer Command Center)

```
┌─────────────────────────────────────────────────────────────────┐
│  SPONSOR REPORT — Lovable (Gold Sponsor)        [Export PDF]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  KEY METRICS                                                    │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐  │
│  │   247   │  │  4.2    │  │   38    │  │    2:15 PM      │  │
│  │ Unique  │  │ Avg Min │  │ Return  │  │  Peak Traffic   │  │
│  │Visitors │  │ Dwell   │  │Visitors │  │                 │  │
│  └─────────┘  └─────────┘  └─────────┘  └─────────────────┘  │
│                                                                 │
│  TRAFFIC OVER TIME                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │    ╭──╮                                                 │   │
│  │   ╭╯  ╰╮         ╭──╮                                  │   │
│  │  ╭╯    ╰╮      ╭╯  ╰╮                                  │   │
│  │ ╭╯      ╰──╮ ╭╯    ╰──╮                                │   │
│  │╯            ╰╯         ╰──╮                             │   │
│  │ 6PM  8PM  10PM  12AM  2AM  4AM  6AM                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  VISITOR BREAKDOWN                                              │
│  By Track: AI/ML (42%) | Web3 (23%) | DevTools (18%) | Other   │
│  By Team Size: Solo (15%) | 2-3 (45%) | 4-5 (40%)             │
│                                                                 │
│  [ Export PDF Report ]  [ Download Raw Data ]                   │
└─────────────────────────────────────────────────────────────────┘
```

*Organizer generates this report and shares the PDF with the sponsor. Sponsors never access the platform directly.*

---

## 5. APPLICATION FLOW

### 5.1 Pre-Event Setup Flow

```
1. VENUE MAPPING
   Admin uploads venue floor plan image
   → Admin places camera positions on floor plan
   → Admin draws zone polygons on each camera view
   → System validates zone coverage (warns about gaps)

2. CAMERA SETUP
   Admin enters RTSP URL for each CCTV camera
   Admin configures drone stream URL
   → System tests each stream (connectivity, resolution, FPS)
   → System stores camera configs in DB

3. SCORING CONFIG
   Admin reviews default scoring weights
   → Admin adjusts weights if needed
   → Admin sets event start/end time
   → System creates time-partitioned tables for activity_logs

4. SPONSOR SETUP
   Admin creates sponsor profiles
   → Admin links sponsors to booth zones
   → System initializes sponsor analytics tables
```

### 5.2 Registration Flow (Day of Event)

```
1. Participant arrives at registration desk
2. Staff opens registration app on tablet
3. Staff points tablet camera at participant's face
4. System detects face via SCRFD
   └─ If no face detected → "Please look at the camera"
   └─ If multiple faces → "Only one person at a time"
5. System extracts 512-dim ArcFace embedding
6. System checks FAISS index for duplicates (prevent double registration)
   └─ If match found (cosine sim > 0.6) → "Already registered as [name]"
7. Staff enters participant info (name, team, track)
8. Staff confirms consent checkbox
9. System stores:
   └─ Embedding → FAISS index (get embedding_id)
   └─ Profile → PostgreSQL participants table
   └─ Initial score row → PostgreSQL scores table
   └─ State → Redis participant:<id> hash
10. System shows confirmation: "Registered: [name]. Tracking active."
11. Participant receives standard hackathon badge and moves on
    — No QR code, no app, no participant-facing anything
```

### 5.3 Real-Time Tracking Flow (During Event)

```
PER CAMERA, EVERY 100-200ms (5-10 FPS):

1. FRAME CAPTURE
   cv2.VideoCapture reads frame from RTSP stream

2. FACE DETECTION + IDENTIFICATION (every 2 seconds, not every frame)
   Frame → SCRFD → detected faces with bounding boxes
   Each face → ArcFace → 512-dim embedding
   Batch query FAISS → top-1 match per face
   If cosine_similarity > 0.5 → identity confirmed
   If < 0.5 → mark as "unknown" (not registered or opted out)

3. PERSON DETECTION + POSE (every frame)
   Frame → YOLO11-Pose → bounding boxes + 17 keypoints + track IDs
   ByteTrack maintains track IDs across frames

4. IDENTITY-TRACK ASSOCIATION
   Match SCRFD face boxes to YOLO person boxes (IoU overlap)
   Each YOLO track gets associated participant_id
   Between face recognition runs, track ID maintains identity

5. ZONE CLASSIFICATION
   Person bounding box centroid → point-in-polygon test
   → Assigns zone_id

6. ACTIVITY CLASSIFICATION (MVP: zone-based)
   Zone type + basic pose heuristics → activity label
   Example: zone_type="coding" + sitting posture → activity="coding"

7. EMIT EVENT
   {participant_id, camera_id, zone_id, activity, bbox, keypoints, timestamp}
   → Push to Redis Stream "activity_stream"

8. SCORING ENGINE (separate process, consumes Redis Stream)
   Reads activity events
   Aggregates time per activity per participant
   Applies scoring weights
   Updates PostgreSQL scores table
   Updates Redis leaderboard sorted set
   Pushes via WebSocket to connected clients
```

### 5.4 Score Calculation Flow

```
Every 60 seconds per participant:

1. Read activity_logs for last 60 seconds for this participant
2. Group by activity type → duration per activity
3. For each activity:
   duration_minutes = count_of_logs * (log_interval_seconds / 60)
   points = duration_minutes * scoring_config[activity].weight
4. Sum all points → period_score
5. total_score = previous_total_score + period_score
6. Update per-activity minute counters
7. Recalculate behavioral tags:
   if coding_minutes / total_minutes > 0.50 → add "Builder"
   if mentoring_minutes / total_minutes > 0.15 → add "Mentor"
   if collaborating_minutes / total_minutes > 0.30 → add "Collaborator"
   if networking_minutes / total_minutes > 0.20 → add "Networker"
   if last_seen_at.hour >= 2 AND last_seen_at.hour <= 5 → add "Night Owl"
   if distinct_team_zones_visited >= 3 → add "Cross-Pollinator"
8. Recalculate rank (ZRANK on Redis leaderboard)
9. Push score update via WebSocket
```

---

## 6. IMPLEMENTATION PLAN

### Phase 1: MVP (Weeks 1-4) — Ship for Buildathon Dallas

**Week 1: Core Pipeline + GCP Setup**
```
Day 1-2: GCP + project setup
  - Create GCE g2-standard-8 VM with NVIDIA L4
  - Install NVIDIA drivers, Docker, NVIDIA Container Toolkit
  - Initialize repo with PROJECT.md, .cursorrules
  - Docker Compose: MediaMTX + PostgreSQL + Redis + FastAPI
  - Database schema migration (Alembic)
  - Test MediaMTX: push RTMP from local machine, verify RTSP output
  
Day 3-4: Face registration module
  - Fork vectornguyen76/face-recognition SCRFD + ArcFace pipeline
  - Build FastAPI endpoint: POST /api/register (with FAISS write lock)
  - FAISS index initialization + persistence
  - Registration UI for tablets (React, supports parallel stations)

Day 5-7: Camera ingestion + tracking with supervision
  - MediaMTX receives RTMP streams, exposes local RTSP
  - Camera worker: sv.get_video_frames_generator for RTSP
  - DEIMv2-wholebody49 → sv.Detections (manual construction, not from_ultralytics)
  - sv.ByteTrack for tracking
  - Face recognition every 2s, track-to-identity mapping
  - Redis Stream for activity events
```

**Week 2: Zone + Scoring**
```
Day 8-9: Zone system with supervision
  - sv.PolygonZone for each zone (define via admin UI or config)
  - sv.LineZone for sponsor booth entry/exit counting
  - Zone occupancy tracking in Redis
  
Day 10-11: Scoring engine
  - Redis Stream consumer
  - Activity aggregation + weight application
  - Score calculation + Redis leaderboard update (1,000 participants)
  - PostgreSQL score persistence
  - Behavioral tag calculation

Day 12-14: CCTV Wall Dashboard — core view
  - Auth/login for organizer access
  - Camera grid layout (ground floor / 1st floor / 2nd floor sections)
  - Live annotated MJPEG streams from camera workers
  - Bounding boxes with names + activity color coding
  - Click-to-inspect: click person box → score card popup
  - WebSocket for live updates
```

**Week 3: Dashboard + Analytics**
```
Day 15-17: Dashboard secondary views
  - Heatmap tab (per-floor zone overlays on floor plan)
  - Leaderboard tab (sortable by total/coding/mentoring/etc, filterable)
  - Energy graph (activity level over time)
  - Zone utilization bars
  - Alert system (zone capacity, mentor booth empty, energy dip)
  - Compare mode for judging (side-by-side participant profiles)

Day 18-19: Sponsor reports + settings
  - Per-sponsor engagement report page
  - PDF export for sponsor reports
  - Camera management UI (add/test streams, view status)
  - Zone polygon editor on camera frame
  - Scoring weight adjustment UI

Day 20-21: Testing + hardening
  - Load test with simulated RTMP streams (scripts/simulate_streams.py)
  - Verify scoring accuracy with 1,000 fake participants
  - WebSocket stability under load
  - Camera worker crash recovery
  - Test ffmpeg relay from laptop to GCP VM
```

**Week 4: Polish + Deploy**
```
Day 22-23: Advanced features
  - Filtering: "show me everyone who mentored 2+ hours"
  - Team comparison view for judging
  - Export all scores as CSV
  - Full profile view with timeline, radar chart, sponsor visits

Day 24-25: GCP deploy prep
  - Build and push Docker images to Artifact Registry
  - Deploy to GCE g2-standard-8 VM
  - Test full pipeline: laptop ffmpeg → RTMP → VM → processing → dashboard
  - Test with real CCTV cameras if available
  - End-to-end dry run: register 10 people, walk around, check scores

Day 26-27: Venue prep
  - Write ffmpeg relay script for all cameras
  - Prepare registration tablets (4-5 devices, bookmarked to registration URL)
  - Create organizer accounts
  - Upload venue floor plans per floor
  - Prepare camera placement plan

Day 28: Buffer
  - Bug fixes, performance tuning
  - Documentation: venue setup runbook
  - Backup/restore verification
```

### Phase 2: Enhancement (Weeks 5-8)

```
- Pose-based activity classification (YOLO keypoints → classifier)
- Sponsor analytics dashboard
- Drone integration + BEV fusion (MATRIX framework)
- Cross-team collaboration detection
- Participant profile cards for LinkedIn sharing
- "Helping others" detection (Person A in Team B's zone)
```

### Phase 3: Platform (Weeks 9-12)

```
- Multi-event support (event_id in all tables)
- Match Day integration API
- Robotics data export (OpenTraj format CSV + JSON)
- Digital twin 2D visualization
- SaaS onboarding flow for other hackathon organizers
- Pricing + billing infrastructure
```

---

## 7. DIRECTORY STRUCTURE

```
spatialscore/
├── PROJECT.md
├── .cursorrules
├── docker-compose.yml
├── README.md
│
├── backend/
│   ├── main.py                    # FastAPI app entry
│   ├── config.py                  # Environment config
│   ├── requirements.txt
│   │
│   ├── api/
│   │   ├── registration.py        # POST /register
│   │   ├── scores.py              # GET /scores/*
│   │   ├── zones.py               # CRUD /zones
│   │   ├── analytics.py           # GET /analytics/*
│   │   ├── sponsors.py            # GET /sponsors/*
│   │   ├── cameras.py             # CRUD /cameras
│   │   ├── export.py              # GET /export/*
│   │   └── websocket.py           # WebSocket handlers
│   │
│   ├── core/
│   │   ├── face_detector.py       # SCRFD wrapper (from vectornguyen76)
│   │   ├── face_recognizer.py     # ArcFace embedding (from vectornguyen76)
│   │   ├── face_matcher.py        # FAISS index (from yakhyo)
│   │   ├── person_tracker.py      # YOLO11-Pose + ByteTrack
│   │   ├── zone_classifier.py     # Point-in-polygon zone detection
│   │   ├── activity_classifier.py # Zone-based (MVP) + pose-based (Phase 2)
│   │   └── scoring_engine.py      # Score calculation + tags
│   │
│   ├── workers/
│   │   ├── camera_worker.py       # One instance per camera stream
│   │   ├── scoring_worker.py      # Consumes activity events, updates scores
│   │   └── heatmap_worker.py      # Periodic heatmap snapshots
│   │
│   ├── db/
│   │   ├── database.py            # PostgreSQL connection
│   │   ├── redis_client.py        # Redis connection
│   │   ├── models.py              # SQLAlchemy models
│   │   └── migrations/            # Alembic migrations
│   │
│   └── utils/
│       ├── geometry.py            # Point-in-polygon, BEV projection
│       └── stream.py              # RTSP stream reader
│
├── dashboard/
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Registration.tsx    # Tablet registration UI
│   │   │   ├── CommandCenter.tsx    # Main organizer dashboard
│   │   │   ├── ParticipantLookup.tsx # Deep-dive into any participant
│   │   │   ├── Leaderboard.tsx      # Full ranked list with filters
│   │   │   ├── SponsorReports.tsx   # Per-sponsor engagement reports
│   │   │   ├── LiveTracking.tsx     # Camera feeds with overlay
│   │   │   ├── AdminSettings.tsx    # Camera + zone + scoring config
│   │   │   └── Login.tsx            # Organizer auth
│   │   ├── components/
│   │   │   ├── Heatmap.tsx
│   │   │   ├── EnergyGraph.tsx
│   │   │   ├── RadarChart.tsx       # Participant profile radar
│   │   │   ├── ActivityTimeline.tsx
│   │   │   ├── ZoneUtilization.tsx
│   │   │   ├── LiveLeaderboard.tsx
│   │   │   └── CameraFeed.tsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts      # WebSocket connection hook
│   │   │   └── useScores.ts         # Score data fetching
│   │   └── utils/
│   │       └── api.ts               # API client
│   └── tailwind.config.js
│
├── models/
│   ├── scrfd_500m.onnx              # Face detection model
│   ├── arcface_r100.onnx            # Face recognition model
│   └── yolo11n-pose.pt              # Person detection + pose model
│
├── scripts/
│   ├── setup_venue.py               # Initialize zones + cameras
│   ├── simulate_streams.py          # Generate fake RTSP streams for testing
│   ├── export_trajectories.py       # Export to OpenTraj format
│   └── benchmark.py                 # Performance benchmarking
│
└── deploy/
    ├── Dockerfile.backend
    ├── Dockerfile.dashboard
    ├── Dockerfile.worker
    └── docker-compose.prod.yml
```

---

## 8. INFRASTRUCTURE

### Google Cloud Platform (Single VM)

```
GCE VM: g2-standard-8
  - 1x NVIDIA L4 GPU (24GB VRAM)
  - 8 vCPU
  - 32GB RAM
  - 200GB pd-ssd boot disk
  - Region: us-central1-a
  - Cost: ~$1.40/hr (~$34 for 24-hour event)
  - OS: Ubuntu 24.04 LTS + NVIDIA Driver 550 + Docker

All services run in Docker Compose on this single VM:
  mediamtx, camera-workers × 10-13, scoring-engine,
  heatmap-worker, api-server, dashboard, postgres, redis

Venue Requirements:
  - 10-13 IP cameras with RTSP output (1080p, PoE)
  - PoE switch(es) per floor
  - Organizer laptop running ffmpeg (RTSP → RTMP relay)
  - Venue internet: 60+ Mbps sustained upload
  - No GPU hardware needed at venue
```

---

*End of Technical Requirements Document*
