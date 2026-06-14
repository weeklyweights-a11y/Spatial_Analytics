# SpatialScore — Build Plan

## Phase Overview

| Phase | Title | Status | Estimated Hours | Dependencies |
|-------|-------|--------|----------------|-------------|
| 1 | Infrastructure + Registration | Complete | 4-5 hours | None |
| 2 | Camera Pipeline + Identity | Complete | 5-6 hours | Phase 1 |
| 3 | Scoring Engine + CCTV Wall | Complete | 5-6 hours | Phase 2 |
| 4 | Heatmap + Analytics + Alerts | Not Started | 4-5 hours | Phase 3 |
| 5 | Sponsors + Judging + Export | Not Started | 3-4 hours | Phase 3 |
| 6 | Ship-Readiness | Not Started | 3-4 hours | Phase 4, 5 |

**Total estimated: 24-30 hours of Cursor implementation time**

Status legend: Not Started | In Progress | Complete | Blocked

---

## Phase 1: Infrastructure + Registration

**Goal:** GCP VM running with Docker Compose. Database migrated. Registration endpoint working — can capture a face, store embedding in FAISS, and persist participant profile. Registration tablet UI functional with parallel station support.

**Key outputs:**
- docker-compose.yml with MediaMTX + PostgreSQL + Redis + FastAPI + React running
- All database tables created via Alembic migration
- POST /api/v1/register accepts face photo, detects face, generates embedding, stores in FAISS with write lock
- Registration React page works on tablet — camera capture, form fields, consent checkbox
- FAISS index persists to disk and loads on restart
- Health check endpoint verifies all services

**What this phase does NOT build:**
- No camera workers (Phase 2)
- No DEIMv2 inference (Phase 2)
- No scoring (Phase 3)
- No CCTV wall (Phase 3)
- No heatmaps (Phase 4)

---

## Phase 2: Camera Pipeline + Identity

**Goal:** Camera workers processing live RTSP streams via DEIMv2 + supervision. Faces recognized and linked to registered participants. Zone classification working. Activity events flowing into Redis Stream. You can push a test RTMP stream from your laptop and see identified, tracked, zone-assigned people in the Redis Stream.

**Key outputs:**
- Camera worker process: reads RTSP from MediaMTX, runs DEIMv2 per frame, tracks with sv.ByteTrack
- DEIMv2-wholebody49 ONNX model loaded and running on GPU, outputting 49 keypoints per person
- SCRFD + ArcFace face pipeline running every 2 seconds, matching against FAISS
- Track-to-identity mapping maintained across frames
- sv.PolygonZone configured for venue zones (loaded from configs/zones.yaml)
- Activity classification: zone type + hand keypoint heuristic
- Events written to Redis Stream with participant_id, zone, activity, timestamp
- Zone occupancy updated in Redis
- Annotated frames stored in Redis (`camera_frame:*`, 5s TTL) for Phase 3 MJPEG serving
- `scripts/simulate_streams.py` for RTMP test streams (10 FPS)

**What this phase does NOT build:**
- No scoring calculation (Phase 3)
- No dashboard UI beyond registration (Phase 3)
- No WebSocket push (Phase 3)
- No heatmaps or energy graphs (Phase 4)
- No sponsor tracking (Phase 5)

---

## Phase 3: Scoring Engine + CCTV Wall

**Goal:** Full pipeline working end-to-end. Scoring engine consumes activity events, calculates weighted scores, assigns behavioral tags. CCTV wall dashboard is live — camera grid with labeled people, click on anyone to see their score card. WebSocket pushes live updates. This is the MVP — if this phase works, you have a shippable product.

**Key outputs:**
- Scoring worker consuming Redis Stream, flushing every 60 seconds
- Weighted score calculation per participant
- Behavioral tag assignment (Builder, Mentor, Collaborator, etc.)
- Scores written to PostgreSQL, leaderboard to Redis
- WebSocket channels: /ws/leaderboard, /ws/tracking/{cam_id}
- CCTV wall page: tiled camera grid organized by floor
- Each camera feed shows annotated MJPEG with labeled bounding boxes
- Click on person's box → score card popup (name, photo, score, rank, radar chart, tags)
- Auth/login with JWT
- API endpoints: /scores/leaderboard, /scores/{id}, /tracking/active

**What this phase does NOT build:**
- No heatmap overlays (Phase 4)
- No energy graph (Phase 4)
- No alerts (Phase 4)
- No leaderboard sorting/filtering (Phase 4)
- No sponsor reports (Phase 5)
- No PDF export (Phase 5)
- No compare mode (Phase 5)

---

## Phase 4: Heatmap + Analytics + Alerts

**Goal:** Organizer has full operational awareness. Heatmap shows real-time crowd density per floor. Energy graph shows activity over time. Alerts fire when zones are full or empty. Leaderboard is sortable and filterable.

**Key outputs:**
- Heatmap worker: periodic snapshots of zone occupancy
- Heatmap page: floor plan SVG per floor with color-coded zone overlays, updated every 10 seconds via WebSocket
- Energy graph: Recharts line chart showing activity level over time
- Zone utilization bars: per-zone capacity percentage
- Alert engine: configurable rules (zone >90% capacity, mentor booth empty >30 min, energy <25%)
- Alerts pushed via WebSocket, displayed as toast notifications on CCTV wall
- Leaderboard page: full 1,000-participant table, sortable by total/coding/mentoring/collaborating/networking, filterable by team/track/tag/floor
- /ws/heatmap and /ws/alerts channels

**What this phase does NOT build:**
- No sponsor booth tracking (Phase 5)
- No PDF report generation (Phase 5)
- No compare mode (Phase 5)
- No trajectory export (Phase 5)

---

## Phase 5: Sponsors + Judging + Export

**Goal:** Sponsor booth engagement tracked and reportable. Participants comparable side-by-side for judging. Data exportable for post-event analysis and robotics training.

**Key outputs:**
- sv.LineZone for sponsor booth entry/exit counting
- Sponsor engagement aggregation: unique visitors, dwell time, return visits, peak hours
- Sponsor report page per sponsor with traffic charts
- PDF export of sponsor reports (reportlab or weasyprint)
- Full participant profile page with timeline, radar chart, tags (Phase 3 — see ParticipantProfile)
- Compare mode: select 2-3 participants, view side-by-side radar charts and scores
- CSV export: all scores, all activity logs
- Trajectory export in OpenTraj format (timestamp, participant_id, x, y, activity)

**What this phase does NOT build:**
- No load testing (Phase 6)
- No venue-specific setup (Phase 6)
- No deployment hardening (Phase 6)

---

## Phase 6: Ship-Readiness

**Goal:** System is production-ready for Buildathon Dallas. Tested at scale, recovery verified, venue prep complete.

**Key outputs:**
- scripts/simulate_streams.py reused from Phase 2 for load testing (13 streams)
- Load test: 13 simulated camera streams, 1,000 fake participants, running for 2+ hours
- Verify: no memory leaks, no VRAM growth, no PostgreSQL bloat
- Crash recovery test: kill and restart each service, verify state recovery
- ffmpeg relay test: push from a real laptop to GCP VM, verify pipeline works end-to-end
- Backup/restore verification: pg_dump to Cloud Storage, restore on fresh VM
- scripts/setup_venue.py: interactive venue configuration (upload floor plans, define zones, configure cameras)
- Registration tablet prep: bookmark URL on 4-5 devices, test concurrent registration
- Create organizer accounts via CLI
- Seed demo data for dry run
- Venue runbook document: step-by-step for event day setup and operations
- README.md with project overview, setup instructions, architecture diagram
- .env.example with all required environment variables

---

## Workflow

1. Read `.cursorrules` and `PROJECT.md` before starting any phase
2. Read the phase spec (`docs/PHASE_N_SPEC.md`) for the current phase
3. Create an implementation plan: list every file to create/modify, what each contains, build order
4. Present the plan and wait for approval before writing code
5. Build the phase, committing after each working feature
6. Test all acceptance criteria in the phase spec
7. Do not start the next phase until all criteria pass
