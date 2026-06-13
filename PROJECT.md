# SpatialScore — Product Spec

## The Problem

Hackathons measure output, not process. Judges see a 3-minute demo and score based on a polished pitch. Someone who mentored 5 teams, debugged critical issues for others, and collaborated across groups gets zero credit if their demo crashes. A freeloader who contributed nothing gets the same "participant" credential as everyone else. Organizers have no visibility into what actually happens during the 12-24 hours. Sponsors pay thousands for booths with zero engagement data.

There is no observability layer for physical hackathon behavior.

## The Solution

SpatialScore gives hackathon organizers a CCTV command center where every participant is identified, tracked, and scored in real time. Fixed CCTV cameras across the venue feed video to a Google Cloud GPU VM. The VM identifies each person by face recognition, tracks them across cameras, classifies what they're doing based on which zone they're in and their body pose (49 keypoints including hands and feet), and calculates a personalized engagement score.

The organizer opens a browser and sees a grid of all camera feeds. Every person has a labeled bounding box with their name, color-coded by activity. Click on anyone in the video — their score card pops up showing total score, rank, activity breakdown, and behavioral tags. No typing, no searching. Pure visual point-and-click surveillance with intelligence overlay.

Participants never see the system. It's an internal organizer tool for judging, awards, operational decisions, and sponsor reporting.

## Scale

- 1,000 participants across 3 floors (ground, 1st, 2nd)
- 10-13 fixed CCTV cameras
- 24-hour continuous operation
- Single GCP GPU VM (NVIDIA L4, 24GB VRAM)

## Architecture

### Infrastructure

Everything runs on one GCE g2-standard-8 VM (NVIDIA L4, 8 vCPU, 32GB RAM, 200GB SSD) in Docker Compose. No managed database services, no external message brokers, no distributed systems.

At the venue: IP cameras output RTSP on local network. An organizer's laptop runs ffmpeg to forward each camera stream as RTMP over the internet to the GCP VM. MediaMTX on the VM receives the RTMP and re-exposes streams as local RTSP for the camera workers.

### The CV Pipeline

**Registration:** Participant shows physical ID at check-in. Registration app captures face → SCRFD detects face → ArcFace generates 512-dim embedding → stored in FAISS IndexFlatIP. Multiple parallel registration stations with a write lock on FAISS.

**Per-camera frame processing (10 FPS):**
1. DEIMv2-wholebody49 detects all persons + extracts 49 keypoints per person (body, hands, feet)
2. supervision ByteTrack maintains persistent track IDs across frames
3. Every 2 seconds: SCRFD detects faces → ArcFace embeds → FAISS matches to registered participant → links track ID to identity
4. supervision PolygonZone determines which zone each person is in
5. Activity classified based on zone type + hand keypoint position (hands forward on table = coding, hands in lap = idle, hands gesturing = collaborating)
6. Event emitted to Redis Stream: `{participant_id, zone, activity, camera_id, timestamp}`

**Scoring engine** consumes Redis Stream every 60 seconds:
- Groups events by participant
- Calculates weighted score: coding × 1.0, collaborating × 1.5, mentoring × 2.0, presenting × 2.0, networking × 1.2, helping_others × 1.8
- Updates PostgreSQL scores table
- Updates Redis leaderboard sorted set
- Calculates behavioral tags: Builder, Mentor, Collaborator, Networker, Night Owl, Cross-Pollinator
- Pushes via WebSocket to connected dashboards

### Models (All ONNX, all on same GPU)

| Model | File | Size | What It Does |
|-------|------|------|-------------|
| SCRFD-10G | scrfd_10g.onnx | 16 MB | Face detection — bounding boxes + 5 landmarks |
| ArcFace-R100 | arcface_r100.onnx | 166 MB | Face embedding — 512-dim vector per face |
| DEIMv2-S wholebody49 | deimv2_s_wholebody49.onnx | ~40 MB | Person detection — bounding boxes + 49 keypoints |

Total GPU VRAM: ~3 GB of 24 GB available.

### Data Storage

| Data | Where | Volume |
|------|-------|--------|
| Participant profiles | PostgreSQL | 1,000 rows |
| Scores | PostgreSQL + Redis cache | 1,000 rows |
| Activity logs | PostgreSQL (hourly partitions) | ~9M rows over 24 hours |
| Face embeddings | FAISS index in RAM + disk backup | ~2 MB |
| Real-time state | Redis hashes + sorted sets | ~100 MB |
| Activity event stream | Redis Streams (rolling 50K) | ~50 MB |
| Backups | Google Cloud Storage | Pushed every 2 hours |
| Registration photos | VM disk, deleted 48h post-event | ~100 MB |

### Dashboard

**Primary view — CCTV Wall:**
- Grid of all camera feeds organized by floor
- Every person has a labeled, color-coded bounding box (green=coding, blue=collaborating, orange=mentoring, purple=presenting, grey=idle)
- Click any person's box → score card popup: name, photo, score, rank, mini radar chart, tags
- Click another person → card updates. Click empty space → card closes.

**Secondary views (tabs):**
- Leaderboard: sortable by total/coding/mentoring/etc, filterable by team/track/tag, compare mode
- Heatmap: per-floor venue layout with zone occupancy overlays
- Analytics: energy graph over time, zone utilization
- Sponsor reports: per-sponsor engagement metrics, PDF export
- Settings: camera management, zone polygon editor, scoring weight config
- Registration: tablet-optimized face capture form (parallel stations)

### API Design

REST endpoints (all auth-protected):
- Registration: POST /register, GET/DELETE /participants/{id}
- Scores: GET /scores/leaderboard, GET /scores/{id}, GET /scores/{id}/timeline, GET /scores/compare
- Tracking: GET /tracking/active, GET /tracking/{id}, GET /tracking/zone/{id}
- Analytics: GET /analytics/heatmap, GET /analytics/energy, GET /analytics/zones
- Sponsors: GET /sponsors/{id}/report, GET /sponsors/{id}/report/pdf
- Config: GET/PUT /config/scoring, POST/GET /cameras, PUT /cameras/{id}/zones
- Export: GET /export/scores (CSV), GET /export/trajectories

WebSocket channels (all auth-protected):
- /ws/leaderboard — pushes every 30s
- /ws/heatmap — pushes every 10s
- /ws/alerts — pushes on trigger
- /ws/tracking/{cam_id} — pushes every 1s (bounding boxes for CCTV wall)
- /ws/participant/{id} — pushes every 30s (for score card live update)

### Database Schema

**participants:** id (UUID PK), name, email, team_name, track, skills[], photo_path, embedding_id (int, FAISS position), registered_at, opted_out

**scores:** participant_id (UUID PK → participants), total_score, coding_minutes, collaborating_minutes, mentoring_minutes, presenting_minutes, networking_minutes, helping_minutes, idle_minutes, tags[], rank, last_zone, last_activity, last_seen_at, updated_at

**activity_logs:** id (BIGSERIAL PK), participant_id (UUID → participants), camera_id, zone_id (UUID → zones), activity, bbox (JSONB), confidence, timestamp. Partitioned by hour.

**zones:** id (UUID PK), name, zone_type (coding/mentoring/presenting/networking/sponsor/food/rest), camera_id, polygon_coords (JSONB), floor (int), capacity, sponsor_id (UUID → sponsors)

**cameras:** id (VARCHAR PK), name, rtsp_url, camera_type, floor, is_active

**scoring_config:** activity (VARCHAR PK), weight (FLOAT), min_dwell_seconds (INT)

**sponsors:** id (UUID PK), name, tier, booth_zone_id (UUID → zones)

**sponsor_engagement:** sponsor_id + hour_bucket (composite PK), unique_visitors, total_visits, avg_dwell_seconds, return_visitors

**heatmap_snapshots:** id (BIGSERIAL PK), timestamp, zone_occupancy (JSONB), total_active, energy_level

**users:** id (UUID PK), username, password_hash, role (admin/operator/viewer)

### Auth + Permissions

Three roles: admin (full access), operator (register + view, no settings), viewer (leaderboard + heatmap only). JWT with 24-hour lifetime. Accounts created via CLI pre-event.

### Scoring

| Activity | Weight | Min Dwell |
|----------|--------|-----------|
| Coding | 1.0 | 2 min |
| Collaborating | 1.5 | 2 min |
| Mentoring | 2.0 | 5 min |
| Presenting | 2.0 | 1 min |
| Networking | 1.2 | 2 min |
| Helping Others | 1.8 | 10 min |
| Sponsor Engagement | 1.0 | 2 min |
| Eating | 0 | — |
| Resting | 0 | — |
| Idle | 0 | — |

**Tags (auto-assigned):**
- Builder: >50% time coding
- Mentor: >15% time mentoring or helping
- Collaborator: >30% time collaborating
- Networker: >20% time networking
- Night Owl: active 2AM-5AM
- Cross-Pollinator: visited 3+ different teams' areas

### Privacy

- Raw video frames never stored — processed in memory, discarded
- Face embeddings (512-dim vectors) are not reversible to face images
- Registration photos deleted 48 hours post-event
- Activity logs anonymized 30 days post-event (participant_id → SHA256 hash)
- Participants opt in during registration, can opt out anytime
- Signage at venue: "This venue uses cameras for event operations"

## Build Phases

### Phase 1: Infrastructure + Registration
GCP VM setup, Docker Compose (MediaMTX + PostgreSQL + Redis + FastAPI + React scaffold), database schema, face registration with SCRFD + ArcFace + FAISS, registration tablet UI with parallel station support.

### Phase 2: Camera Pipeline + Identity
Camera workers consuming RTSP via MediaMTX, DEIMv2-wholebody49 + supervision for detection and tracking, face recognition linking tracks to identities, zone detection with PolygonZone, activity events flowing to Redis Stream.

### Phase 3: Scoring Engine + CCTV Wall
Scoring worker consuming Redis Stream, weighted scores, behavioral tags, leaderboard. CCTV wall dashboard with annotated camera grid, bounding boxes with names, click-to-inspect score cards, WebSocket live updates.

### Phase 4: Heatmap + Analytics + Alerts
Per-floor heatmap overlays, energy graph, zone utilization, alert engine (zone capacity, mentor booth empty, energy dip), leaderboard with sorting/filtering/compare mode.

### Phase 5: Sponsors + Judging + Export
LineZone for sponsor booth entry/exit counting, sponsor engagement reports with PDF export, full participant profile with timeline, compare mode for judging, CSV export for scores and trajectories.

### Phase 6: Ship-Readiness
Load testing with simulated streams (1,000 participants), crash recovery testing, ffmpeg relay testing laptop-to-GCP, venue runbook, registration tablet prep, backup/restore verification, demo data seeding, README.

## Competitive Context

**What exists today:** Devpost, HackerEarth, Judgify — all digital, submission-based. Track git commits, not physical behavior. Zero awareness of collaboration, mentoring, or engagement.

**WiFi-based spatial analytics:** Meshh (acquired 2021) tracked dwell time via WiFi probes. Too coarse — can't identify individuals or classify activities.

**Camera-based event analytics:** StrataVision ($16.7M Series A), Engage Vision (acquired 2025). Focus on retail and general events, not hackathon-specific scoring.

**Academic validation:** ICGJ '24 paper used wearable badges to track hackathon collaboration — proved the problem is real, but badges don't scale. "From Cues to Engagement" (Jan 2026) validates CV-based audience analytics as a commercial opportunity.

**Our angle:** Nobody combines face recognition + whole-body pose estimation + zone-based activity classification + personalized scoring for hackathons. The building blocks exist (supervision, DEIMv2, ArcFace). The novel contribution is the integration and the scoring application.

## Post-Hackathon Value

**For robotics:** The trajectory + activity-labeled dataset (1,000 people, 24 hours, 3 floors) is training data for social robot navigation, pedestrian trajectory prediction, and world models for embodied AI. Export in OpenTraj format.

**As a product:** SpatialScore becomes a SaaS for hackathon organizers, conferences, and corporate events. Multi-tenant architecture in Phase 4+ of the product roadmap. NVIDIA DeepStream upgrade path for 50+ camera deployments.
