# Phase 4: Heatmap + Analytics + Alerts

## What This Phase Does

Give the organizer full operational awareness beyond the CCTV wall. The heatmap tab shows real-time crowd density on each floor's venue layout — zones light up red when packed, stay grey when empty. The analytics tab shows energy over time and zone utilization history so the organizer can spot trends ("coding energy dipped at 2AM, spiked after we sent pizza at 2:30AM"). The alert engine fires real-time warnings when zones hit capacity, mentor booth sits empty too long, or overall energy drops below a threshold — these appear as toast notifications on the CCTV wall so the organizer can act immediately without switching tabs. The leaderboard gets full sorting, filtering, and a compare mode for judging. Settings gets a visual zone polygon editor so zones can be defined by drawing on camera frames instead of editing YAML coordinates.

By the end of this phase, the organizer has a command center: CCTV wall for live monitoring (Phase 3), heatmap for spatial awareness (this phase), analytics for trends (this phase), alerts for proactive operations (this phase), and a leaderboard for judging prep (this phase).

## Prerequisites

- Phase 3 complete and all acceptance criteria passing
- Scoring engine running and updating scores every 60 seconds
- CCTV wall dashboard functional with click-to-inspect score cards
- WebSocket channels working (/ws/leaderboard, /ws/tracking, /ws/participant)
- At least 2 simulated camera streams with 5+ registered participants for testing
- Zone occupancy data flowing into Redis (from camera workers via sv.PolygonZone in Phase 2)

---

## Resources to Download + Install (Phase 4 additions)

### Model Weights

No new model downloads. All models remain from Phase 1-2.

### Python Libraries (additions to requirements.txt)

No new Python dependencies. Everything needed (FastAPI, Redis, SQLAlchemy, supervision, loguru) is already installed from Phases 1-3.

### npm Packages (additions to package.json)

D3.js was already added in Phase 3 as a shell dependency. No new npm packages needed.

If D3.js was not added in Phase 3:
```json
{
  "dependencies": {
    "d3": "^7.9"
  },
  "devDependencies": {
    "@types/d3": "^7.4"
  }
}
```

### Code Patterns

**Heatmap rendering with D3.js:**
- Study D3.js choropleth/area map examples from https://d3js.org/
- Pattern: load SVG floor plan as background → overlay colored polygons on zones → update polygon fill color based on occupancy percentage → animate transitions on data update
- Each zone polygon in the heatmap corresponds to the same polygon defined in zones.yaml, but mapped to floor plan coordinates (separate from camera-frame coordinates)

**From [lewjiayi/Crowd-Analysis](https://github.com/lewjiayi/Crowd-Analysis):**
- Study their energy graph computation: how they calculate "crowd activity energy" from detection counts over time
- Study their optical flow / heatmap blending with OpenCV — we won't use OpenCV for rendering (we use D3 in the browser), but the concept of "accumulate positions → render as heat" informs our approach
- We compute energy on the backend and render in the browser with Recharts — we don't use their rendering code

**Alert engine pattern — no specific repo:**
- Simple rule-based system: each rule is a function that takes current metrics and returns an alert or None
- Rules are evaluated every heatmap snapshot cycle (every 10 seconds)
- Alerts deduplicated with cooldown timers (don't fire the same alert every 10 seconds)
- Alerts pushed via /ws/alerts WebSocket channel

### Docker Images

No new Docker images.

### Venue Floor Plans

Before this phase can be fully tested, the organizer needs floor plan images — one PNG/SVG per floor. These are uploaded via the Settings page and stored in `data/venue/`:
```
data/venue/
├── floor_0_ground.png    — ground floor layout
├── floor_1.png           — 1st floor layout
└── floor_2.png           — 2nd floor layout
```

For development/testing, create simple placeholder floor plans — even hand-drawn rectangles work. The real venue floor plans come during Phase 6 (ship-readiness) after visiting the venue.

**Floor plan coordinate mapping:** Zone polygons exist in two coordinate systems:
1. **Camera-frame coordinates** — used by sv.PolygonZone in camera workers (Phase 2). These are pixel coordinates in the camera's video frame.
2. **Floor-plan coordinates** — used by the heatmap in the dashboard. These are pixel coordinates on the floor plan image.

These are different because a camera sees the room from an angle, while the floor plan is top-down. The zones.yaml needs both:
```yaml
zones:
  - name: "Coding Zone A"
    camera_polygon: [[100, 50], [600, 50], [600, 400], [100, 400]]    # camera-frame pixels
    floor_polygon: [[200, 150], [450, 150], [450, 300], [200, 300]]   # floor-plan pixels
    floor: 0
```

For MVP, these coordinate mappings are manual (measured by looking at the camera feed and the floor plan). An automated calibration tool would be a Phase 5+ feature.

---

## Section 1: Heatmap Worker

### What to build

`backend/workers/heatmap_worker.py` — a periodic process that snapshots the current venue state every 10 seconds and stores it for the heatmap and analytics.

**What it does every 10 seconds:**

1. Read zone occupancy from Redis: `HGETALL zone_occupancy` — gives `{zone_name: person_count}` for every zone
2. Read total active participants: count all `participant:*` keys in Redis where `last_seen` is within the last 5 minutes
3. Calculate energy level: `energy = total_active / total_registered` capped at 1.0. This is a simple metric — the percentage of registered participants who are currently active. Alternative energy formula (better): `energy = sum(zone_occupancy * zone_weight) / (total_registered * max_zone_weight)` where coding/collaborating zones have higher weight than food/rest zones.
4. Build zone occupancy snapshot:
   ```python
   snapshot = {
       "zones": {
           "Coding Zone A": {"count": 34, "capacity": 50, "pct": 68, "floor": 0},
           "Mentor Booth": {"count": 2, "capacity": 10, "pct": 20, "floor": 1},
           ...
       },
       "total_active": 847,
       "total_registered": 1000,
       "energy_level": 0.73,
       "timestamp": "2026-07-15T22:30:00Z"
   }
   ```
5. Store current snapshot in Redis: `SET heatmap:current {json}` — overwritten every cycle
6. Store historical snapshot in PostgreSQL: INSERT into heatmap_snapshots table (for analytics charts)
7. Publish to Redis Pub/Sub channel `heatmap_updated` — triggers WebSocket push to dashboards
8. Run alert rules (see Section 5)

**Docker Compose:** Replace the existing heatmap-worker placeholder or update its command:
```yaml
heatmap-worker:
  build: ./backend
  command: python -m workers.heatmap_worker
  depends_on: [postgres, redis]
  environment:
    DATABASE_URL: postgresql+asyncpg://...
    REDIS_URL: redis://redis:6379
    HEATMAP_SNAPSHOT_INTERVAL: 10
    LOG_LEVEL: INFO
  restart: always
```

No GPU access needed — pure data aggregation.

---

## Section 2: Heatmap API Endpoints

### What to build

**GET /api/v1/analytics/heatmap**
- Returns current heatmap snapshot
- Source: Redis `heatmap:current`
- Response:
  ```json
  {
    "data": {
      "zones": {
        "Coding Zone A": {"count": 34, "capacity": 50, "pct": 68, "floor": 0},
        ...
      },
      "total_active": 847,
      "energy_level": 0.73,
      "timestamp": "2026-07-15T22:30:00Z"
    }
  }
  ```
- Auth: admin, operator, viewer
- Cache: Redis (already there as `heatmap:current`), no additional caching needed

**GET /api/v1/analytics/energy**
- Query params: `?from=2026-07-15T18:00:00Z&to=2026-07-16T06:00:00Z&interval=30` (interval in minutes)
- Returns energy level data points over time for charting
- Source: heatmap_snapshots table, aggregated to requested interval
- Response:
  ```json
  {
    "data": {
      "points": [
        {"timestamp": "2026-07-15T18:00:00Z", "energy": 0.45, "active": 450},
        {"timestamp": "2026-07-15T18:30:00Z", "energy": 0.62, "active": 620},
        ...
      ],
      "from": "...",
      "to": "...",
      "interval_minutes": 30
    }
  }
  ```
- Auth: admin, operator, viewer
- Performance: query against heatmap_snapshots table. With a snapshot every 10 seconds over 24 hours = ~8,640 rows. Aggregating to 30-minute intervals = 48 data points. Fast query.

**GET /api/v1/analytics/zones**
- Query params: `?from=...&to=...&floor=0`
- Returns per-zone occupancy over time
- Source: heatmap_snapshots table, extract zone occupancy from JSONB
- Response:
  ```json
  {
    "data": {
      "zones": {
        "Coding Zone A": [
          {"timestamp": "18:00", "count": 20, "pct": 40},
          {"timestamp": "18:30", "count": 35, "pct": 70},
          ...
        ],
        ...
      },
      "floor": 0
    }
  }
  ```
- Auth: admin, operator, viewer

**GET /api/v1/venues/floors**
- Returns list of floors with their floor plan image URLs
- Source: scan data/venue/ directory for floor plan files
- Response:
  ```json
  {
    "data": {
      "floors": [
        {"floor": 0, "name": "Ground Floor", "image_url": "/static/venue/floor_0_ground.png"},
        {"floor": 1, "name": "1st Floor", "image_url": "/static/venue/floor_1.png"},
        {"floor": 2, "name": "2nd Floor", "image_url": "/static/venue/floor_2.png"}
      ]
    }
  }
  ```

**Static file serving:** Mount `data/venue/` as a static directory in FastAPI so floor plan images are accessible via HTTP:
```python
app.mount("/static/venue", StaticFiles(directory="data/venue"), name="venue")
```

---

## Section 3: WebSocket Channel — Heatmap + Alerts

### What to build

**Channel: /ws/heatmap**
- Push interval: every 10 seconds (triggered by heatmap worker via Redis Pub/Sub `heatmap_updated`)
- Payload: same as GET /analytics/heatmap response — full zone occupancy + energy level
- Auth: JWT in query param

**Channel: /ws/alerts**
- Push: on-event (when an alert fires, not on a fixed interval)
- Payload:
  ```json
  {
    "type": "alert",
    "id": "alert-uuid",
    "severity": "warning",
    "message": "Coding Zone A at 95% capacity (47/50)",
    "zone": "Coding Zone A",
    "floor": 0,
    "timestamp": "2026-07-15T22:30:10Z"
  }
  ```
- Auth: JWT in query param
- The alert is published to Redis Pub/Sub channel `alerts` by the heatmap worker. The WebSocket handler subscribes and forwards to connected clients.

**Update /ws/leaderboard (already exists from Phase 3):**
- No changes to the channel itself
- But the leaderboard endpoint and WebSocket now support the additional query params added in Section 6 (sorting, filtering)

---

## Section 4: Heatmap Dashboard Page

### What to build

`dashboard/src/pages/Heatmap.tsx` — floor-by-floor spatial visualization of crowd density.

**Layout:**
- Floor selector tabs at top: "Ground Floor" | "1st Floor" | "2nd Floor"
- Main area: floor plan image with zone overlays
- Sidebar: zone list with occupancy numbers and capacity bars
- Bottom: mini energy graph (last 2 hours)

**Floor plan rendering with D3.js:**
1. Load floor plan image as the background (`<img>` or SVG `<image>`)
2. Overlay an SVG layer on top of the image
3. For each zone on the selected floor, draw a polygon using `floor_polygon` coordinates from zones data
4. Fill each polygon with a color based on occupancy percentage:
   - 0-30%: green (#22c55e, 30% opacity)
   - 30-60%: yellow (#eab308, 40% opacity)
   - 60-85%: orange (#f97316, 50% opacity)
   - 85-100%: red (#ef4444, 60% opacity)
5. Display zone name and person count as text labels centered on each polygon
6. Animate color transitions on data update (D3 transition, 500ms)

**Live updates:**
- Subscribe to /ws/heatmap — update polygon fills and count labels every 10 seconds
- Smooth color transitions using D3 transition API

**Zone sidebar:**
- List each zone on the selected floor
- Show: zone name, current count / capacity, utilization bar (progress bar)
- Click on a zone in the sidebar → the corresponding polygon on the floor plan pulses/highlights
- Click on a polygon on the floor plan → the zone in the sidebar scrolls into view and highlights

**Mini energy graph:**
- Recharts LineChart showing energy_level over the last 2 hours
- Data from GET /analytics/energy?from={2_hours_ago}&to={now}&interval=5
- Updates when new heatmap data arrives via WebSocket

**Components to build:**

`dashboard/src/components/HeatmapOverlay.tsx` — the D3 floor plan + polygon overlay
- Props: floorPlanUrl, zones (with polygons + occupancy), selectedZone
- D3 renders inside a React ref (useRef + useEffect pattern)
- Handles click events on polygons

`dashboard/src/components/ZoneSidebar.tsx` — zone list with utilization bars
- Props: zones, selectedZone, onZoneClick
- Recharts or simple divs for utilization bars

---

## Section 5: Alert Engine

### What to build

Alert logic runs inside the heatmap worker (not a separate service). After each snapshot, evaluate alert rules.

**Alert rule structure:**
```python
@dataclass
class AlertRule:
    name: str                    # unique rule identifier
    check: Callable              # function that takes snapshot, returns alert or None
    severity: str                # "info", "warning", "critical"
    cooldown_seconds: int        # don't fire again within this window
    last_fired: datetime | None  # last time this rule fired
```

**Rules to implement:**

1. **Zone capacity warning** — fires when any zone exceeds 90% capacity
   - Severity: warning
   - Cooldown: 600 seconds (10 min) per zone
   - Message: "{zone_name} at {pct}% capacity ({count}/{capacity})"
   - Applies per-zone: Coding Zone A can fire independently of Coding Zone B

2. **Mentor booth empty** — fires when any mentoring zone has 0 people for 30+ minutes
   - Severity: warning
   - Cooldown: 1800 seconds (30 min)
   - Message: "Mentor booth on floor {floor} empty for {minutes} minutes"
   - Track empty duration: store `zone_empty_since:{zone_name}` in Redis. Set when count drops to 0, delete when count rises above 0. Check duration on each snapshot.

3. **Energy dip** — fires when overall energy level drops below 25%
   - Severity: info
   - Cooldown: 1800 seconds (30 min)
   - Message: "Event energy at {pct}% — consider food, music, or an announcement"

4. **Zone completely empty** — fires when a coding or networking zone has 0 people
   - Severity: info
   - Cooldown: 3600 seconds (1 hour) per zone
   - Message: "{zone_name} is completely empty"

5. **Sustained high load** — fires when a zone stays above 85% for 30+ minutes
   - Severity: warning
   - Cooldown: 1800 seconds (30 min)
   - Message: "{zone_name} has been above 85% capacity for {minutes} minutes — consider directing people elsewhere"
   - Track sustained duration similar to empty duration

**Alert persistence:**
- Alerts are written to a Redis list: `LPUSH alerts {json}` with LTRIM to keep last 100
- Also written to PostgreSQL alerts table (create in migration):
  ```sql
  CREATE TABLE alerts (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      rule_name VARCHAR(100) NOT NULL,
      severity VARCHAR(20) NOT NULL,
      message TEXT NOT NULL,
      zone VARCHAR(100),
      floor INTEGER,
      fired_at TIMESTAMP NOT NULL DEFAULT NOW(),
      acknowledged BOOLEAN DEFAULT FALSE
  );
  ```
- The API can query historical alerts for the organizer to review

**Alert delivery:**
- Published to Redis Pub/Sub channel `alerts`
- WebSocket handler picks up and pushes to all /ws/alerts subscribers
- Dashboard renders as toast notification on the CCTV wall page

**API endpoint for alerts:**

**GET /api/v1/alerts**
- Query params: `?severity=warning&acknowledged=false&limit=50`
- Returns list of alerts, most recent first
- Auth: admin, operator

**PUT /api/v1/alerts/{id}/acknowledge**
- Marks an alert as acknowledged (organizer has seen and acted on it)
- Auth: admin, operator

---

## Section 6: Enhanced Leaderboard

### What to build

Upgrade the Phase 3 mini leaderboard into a full-featured leaderboard page with sorting, filtering, and compare mode.

`dashboard/src/pages/Leaderboard.tsx` — full leaderboard page.

**Layout:**
- Top bar: sort controls, filter controls, compare toggle
- Main area: paginated table of all 1,000 participants
- Compare panel: when compare mode is active, shows side-by-side radar charts

**Sort controls:**
- Dropdown: "Sort by" → Total Score, Coding, Collaborating, Mentoring, Presenting, Networking
- Toggle: Ascending / Descending
- Implemented via query params to GET /api/v1/scores/leaderboard?sort_by=mentoring&sort_order=desc

**Filter controls:**
- Track filter: dropdown → AI/ML, Web3, DevTools, FinTech, Health, Open, All
- Tag filter: multi-select badges → Builder, Mentor, Collaborator, Networker, Night Owl, Cross-Pollinator
- Floor filter: dropdown → Ground, 1st, 2nd, All (filters by participant's most frequent floor)
- Team search: text input → filters by team_name (partial match)
- All filters passed as query params to the leaderboard API

**Table columns:**
- Rank | Name | Team | Track | Score | Current Activity | Current Zone | Tags
- Each row is clickable → navigates to /participant/{id}
- Current Activity shows colored dot matching CCTV wall colors

**Pagination:**
- 50 participants per page
- Page navigation at bottom
- Total count shown: "Showing 1-50 of 1,000"

**Compare mode:**
- Toggle button: "Compare" ON/OFF
- When ON, each table row gets a checkbox
- Select 2-3 participants → "Compare Selected" button appears
- Clicking "Compare Selected" opens a panel showing:
  - Names side by side
  - Radar charts side by side (Recharts)
  - Score breakdown table: each activity's minutes and points
  - Tags listed
- Useful during judging: "Compare the top 3 mentors"

**API changes:**

Update GET /api/v1/scores/leaderboard to support:
- `?sort_by=total_score|coding|mentoring|collaborating|presenting|networking|helping`
- `?sort_order=asc|desc`
- `?track=ai_ml`
- `?tag=mentor` (can be repeated: `?tag=mentor&tag=builder`)
- `?team=alpha` (partial match)
- `?floor=0`
- `?page=1&per_page=50`

The API constructs a SQL query with dynamic ORDER BY and WHERE clauses. Use parameterized queries to prevent SQL injection.

**GET /api/v1/scores/compare?ids=uuid1,uuid2,uuid3**
- Returns full score breakdown for 2-3 participants in a single response
- Source: scores table + participants table JOIN
- Max 5 IDs per request (rate limit to prevent abuse)

---

## Section 7: CCTV Wall — Alerts Integration

### What to build

Add the alerts feed to the CCTV wall page (Phase 3). Alerts are the missing piece that makes the CCTV wall a true command center.

**Toast notifications:**
- Subscribe to /ws/alerts on the CCTV wall page
- When an alert arrives, show a toast notification in the top-right corner
- Toast styling by severity:
  - info: blue background, info icon
  - warning: orange background, warning triangle icon
  - critical: red background, alert icon
- Toasts auto-dismiss after 10 seconds, or click to dismiss
- Maximum 3 toasts visible simultaneously (oldest dismissed when 4th arrives)

**Alerts sidebar panel:**
- The CCTV wall already has a sidebar (Phase 3 — mini leaderboard + alerts placeholder)
- Replace the "No alerts" placeholder with the real AlertsFeed component
- Show last 10 alerts in reverse chronological order
- Each alert shows: severity icon, message, time ago ("2 min ago")
- Click "Acknowledge" on an alert → calls PUT /api/v1/alerts/{id}/acknowledge → alert greys out

**Sound notification (optional but recommended):**
- Play a subtle notification sound when a warning or critical alert arrives
- Use the Web Audio API: `new Audio('/sounds/alert.mp3').play()`
- Include a mute toggle in the CCTV wall header

---

## Section 8: Settings — Zone Polygon Editor

### What to build

`dashboard/src/pages/Settings.tsx` → Zone Editor tab — visual tool for drawing zone polygons on camera frames.

**How it works:**
1. Organizer selects a camera from a dropdown
2. A snapshot from that camera (single MJPEG frame) is displayed
3. Organizer clicks points on the image to draw a polygon
4. After closing the polygon (clicking near the first point), a form appears: zone name, zone type (dropdown), floor, capacity
5. "Save Zone" → calls POST /api/v1/zones with camera_id, polygon_coords (in camera-frame pixels), floor, zone_type, capacity
6. Existing zones for the selected camera are shown as semi-transparent overlays on the snapshot
7. Click an existing zone to edit (drag points) or delete

**Technical approach:**
- Canvas-based: render the camera snapshot on an HTML5 canvas
- Polygon drawing: click events capture (x, y) coordinates on the canvas
- Draw lines between points as the user clicks
- Double-click or click near first point to close the polygon
- After closing, fill the polygon with semi-transparent color
- Save button sends the array of (x, y) points to the API

**API endpoints for zone management:**

POST /api/v1/zones — create a new zone
```json
{
  "name": "Coding Zone A",
  "zone_type": "coding",
  "camera_id": "CAM-01",
  "polygon_coords": [[100, 50], [600, 50], [600, 400], [100, 400]],
  "floor_polygon": [[200, 150], [450, 150], [450, 300], [200, 300]],
  "floor": 0,
  "capacity": 50
}
```

PUT /api/v1/zones/{id} — update zone polygon or properties

DELETE /api/v1/zones/{id} — remove a zone

GET /api/v1/zones?camera_id=CAM-01 — list zones for a camera

**Camera snapshot endpoint:**
GET /api/v1/cameras/{id}/snapshot — returns a single JPEG frame from the camera
- Source: read `camera_frame:{camera_id}` from Redis (the same frame the MJPEG stream uses)
- Returns: image/jpeg
- Used by the zone editor to show a static frame to draw on

**Zone reload:** When zones are created/updated/deleted via the API, the camera workers need to reload their zone definitions. Publish to Redis Pub/Sub channel `zones_updated`. Camera workers subscribe to this channel and reload zones from the database when triggered. This avoids restarting camera workers when zones change.

---

## Section 9: Settings — Scoring Weight Editor

### What to build

A section in the Settings page where the organizer can adjust scoring weights.

**UI:**
- Table of activity types with current weights
- Each weight is an editable number input (slider or text field)
- "Save" button → calls PUT /api/v1/config/scoring
- Warning: "Changing weights will trigger a full score recalculation for all participants. This may take up to 2 minutes."

**Backend flow when weights change:**
1. PUT /api/v1/config/scoring updates the scoring_config table
2. Publish to Redis Pub/Sub channel `scoring_config_updated`
3. Scoring worker subscribes to this channel, reloads weights from DB
4. Next scoring cycle uses new weights
5. Optionally: trigger a full recalculation — read all activity_logs, recalculate every participant's total score from scratch with new weights. This is expensive (9M rows) but ensures consistency. Run as a background task, not blocking the API response.

---

## Section 10: Database Changes

### What to build

Alembic migration for new tables and columns needed in Phase 4.

**New table — alerts:**
```sql
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_name VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    message TEXT NOT NULL,
    zone VARCHAR(100),
    floor INTEGER,
    fired_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by UUID REFERENCES users(id),
    acknowledged_at TIMESTAMP
);

CREATE INDEX idx_alerts_fired_at ON alerts(fired_at DESC);
CREATE INDEX idx_alerts_severity ON alerts(severity, acknowledged);
```

**Update zones table** — add floor_polygon column:
```sql
ALTER TABLE zones ADD COLUMN floor_polygon JSONB;
```

This column stores the polygon coordinates mapped to the floor plan image (separate from the camera-frame polygon_coords).

---

## Section 11: Logging + Monitoring Extensions

### What to build

**Heatmap worker logs:**
- `INFO` every snapshot: "Heatmap snapshot: active=847, energy=0.73, zones={Coding A: 34, Mentor: 2, ...}"
- `INFO` on alert fired: "Alert fired: rule=zone_capacity, zone=Coding Zone A, severity=warning, message=..."
- `WARNING` when energy drops below 25%: "Energy dip: level=0.18, threshold=0.25"
- `ERROR` if PostgreSQL insert fails for snapshot: "Heatmap snapshot save failed: {error}"

**Health check extension:**
- Add heatmap worker heartbeat to Redis: `HSET worker_status:heatmap last_heartbeat {timestamp}`
- Health endpoint checks heatmap worker heartbeat (stale if >30 seconds)

**Metrics extension:**
- GET /api/v1/metrics now also reports:
  - `heatmap_snapshots_total`: total snapshots stored
  - `alerts_fired_total`: total alerts fired
  - `alerts_unacknowledged`: current count of unacknowledged alerts
  - `energy_level_current`: current energy level

---

## Section 12: Caching Strategy for Analytics

### What to build

Analytics queries hit the heatmap_snapshots table which grows continuously. Add caching to prevent slow queries.

**Energy graph caching:**
- Cache the response of GET /analytics/energy in Redis with key `cache:energy:{from}:{to}:{interval}`
- TTL: 60 seconds (energy data changes every 10 seconds, but a 60-second cache is fine for charts)
- Invalidate on new heatmap snapshot (not needed — TTL handles it)

**Zone analytics caching:**
- Same pattern: cache in Redis with key `cache:zones:{from}:{to}:{floor}`
- TTL: 60 seconds

**Heatmap caching:**
- Already cached: Redis `heatmap:current` is the live cache, updated every 10 seconds by the heatmap worker
- GET /analytics/heatmap reads directly from Redis — no PostgreSQL query needed

**Leaderboard caching:**
- The leaderboard is already in Redis (sorted set from Phase 3)
- But the enriched leaderboard (with names, teams, tags) requires a JOIN query
- Cache the enriched leaderboard response in Redis: `cache:leaderboard:{sort_by}:{sort_order}:{page}`
- TTL: 30 seconds (matches WebSocket push interval)
- Invalidate when scoring engine signals `scores_updated`

---

## Section 13: Rate Limiting Updates

### What to build

Add rate limits for new endpoints:

```python
@app.get("/api/v1/analytics/energy")
@limiter.limit("30/minute")      # Analytics queries

@app.get("/api/v1/analytics/zones")
@limiter.limit("30/minute")

@app.get("/api/v1/alerts")
@limiter.limit("30/minute")

@app.post("/api/v1/zones")
@limiter.limit("10/minute")      # Zone creation

@app.put("/api/v1/config/scoring")
@limiter.limit("2/minute")       # Scoring weight changes (already in Phase 1)

@app.get("/api/v1/cameras/{id}/snapshot")
@limiter.limit("30/minute")      # Camera snapshot for zone editor
```

---

## Section 14: Tests for Phase 4

### What to build

**Unit tests:**
- `tests/unit/test_alert_engine.py`:
  - Zone at 91% capacity → zone_capacity alert fires
  - Zone at 89% capacity → no alert
  - Same zone at 91% within cooldown period → no duplicate alert
  - Zone at 91% after cooldown expires → alert fires again
  - Energy at 0.20 → energy_dip alert fires
  - Energy at 0.30 → no alert
  - Mentor zone empty for 31 minutes → mentor_empty alert fires
  - Mentor zone empty for 29 minutes → no alert

- `tests/unit/test_heatmap_worker.py`:
  - Given zone occupancy data in Redis, verify snapshot contains correct counts and percentages
  - Verify energy calculation: 500 active of 1000 registered → energy = 0.50

**Integration tests:**
- `tests/integration/test_heatmap_pipeline.py`:
  - Start heatmap worker, wait 15 seconds, verify heatmap_snapshots table has at least 1 row
  - Verify GET /analytics/heatmap returns valid zone data
  - Verify GET /analytics/energy returns data points

- `tests/integration/test_alerts.py`:
  - Set zone occupancy to 95% in Redis, trigger heatmap snapshot, verify alert appears in alerts table
  - Verify /ws/alerts WebSocket receives the alert

- `tests/integration/test_leaderboard_filters.py`:
  - Seed 10 participants with different tracks and tags
  - GET /scores/leaderboard?track=ai_ml → verify only AI/ML participants returned
  - GET /scores/leaderboard?tag=mentor → verify only Mentor-tagged participants returned
  - GET /scores/leaderboard?sort_by=mentoring → verify sorted by mentoring minutes
  - GET /scores/compare?ids=uuid1,uuid2 → verify both participants returned with full breakdowns

- `tests/integration/test_zone_crud.py`:
  - POST /zones → create zone, verify in DB
  - PUT /zones/{id} → update polygon, verify in DB
  - DELETE /zones/{id} → verify removed

---

## What NOT to Build in This Phase

- No sponsor entry/exit counting with sv.LineZone — zone counting (PolygonZone) handles sponsor zone occupancy, but specific in/out tracking is Phase 5
- No sponsor engagement reports or PDF export (Phase 5)
- No trajectory export (Phase 5)
- No full participant timeline view enhancements (Phase 5 — the basic timeline from Phase 3 remains)
- No load testing with 1,000 participants (Phase 6)
- No venue-specific setup or runbook (Phase 6)
- No automated camera calibration or floor-plan-to-camera coordinate mapping tool

---

## Acceptance Criteria

**Heatmap:**
- [ ] Heatmap worker runs and stores snapshots in heatmap_snapshots table every 10 seconds
- [ ] GET /analytics/heatmap returns zone occupancy with correct counts and percentages
- [ ] Heatmap page shows floor plan image with colored zone overlays
- [ ] Zone colors update based on occupancy: green (<30%), yellow (30-60%), orange (60-85%), red (>85%)
- [ ] Floor selector tabs switch between ground floor, 1st floor, and 2nd floor
- [ ] Zone overlays update live via /ws/heatmap (no manual refresh needed)
- [ ] Zone sidebar shows list of zones with utilization bars
- [ ] Clicking a zone in sidebar highlights the polygon on the floor plan

**Energy + Analytics:**
- [ ] GET /analytics/energy returns data points over a time range
- [ ] Energy graph (Recharts LineChart) shows energy level over the last 2 hours on the heatmap page
- [ ] GET /analytics/zones returns per-zone occupancy over time
- [ ] Analytics page shows zone utilization charts

**Alerts:**
- [ ] Alert engine fires zone_capacity alert when a zone exceeds 90% capacity
- [ ] Alert engine fires mentor_empty alert when mentor zone is empty for 30+ minutes
- [ ] Alert engine fires energy_dip alert when energy drops below 25%
- [ ] Alert cooldowns work: same alert doesn't fire twice within cooldown period
- [ ] Alerts appear as toast notifications on the CCTV wall page via /ws/alerts
- [ ] Alerts feed in CCTV wall sidebar shows recent alerts with severity icons
- [ ] GET /alerts returns alert history
- [ ] PUT /alerts/{id}/acknowledge marks alert as acknowledged

**Leaderboard:**
- [ ] Leaderboard page shows all 1,000 participants in a paginated table (50 per page)
- [ ] Sorting works: sort by total score, coding, mentoring, collaborating, networking
- [ ] Filtering works: filter by track, tag, floor, team name
- [ ] Compare mode: select 2-3 participants, view side-by-side radar charts and score breakdowns
- [ ] GET /scores/compare returns data for 2-3 participants

**Settings:**
- [ ] Zone polygon editor: select a camera, see a snapshot, draw polygon by clicking points, save zone
- [ ] Existing zones shown as overlays on camera snapshot
- [ ] Zone CRUD via API works: create, update, delete
- [ ] Camera workers reload zones when zones are created/updated/deleted (no restart required)
- [ ] Scoring weight editor: view current weights, modify, save
- [ ] After changing weights, scoring engine uses new weights in next cycle

**Infrastructure:**
- [ ] Heatmap worker heartbeat appears in health check
- [ ] Analytics endpoint responses are cached in Redis (verify response time <50ms after first call)
- [ ] Rate limiting applied to new endpoints
- [ ] All new unit and integration tests pass

---

## How to Give This to Cursor

```
Read .cursorrules, PROJECT.md, and docs/PHASE_4_SPEC.md. This is Phase 4 of SpatialScore.
Phases 1-3 are complete — registration, camera pipeline, face identity, zone detection,
scoring engine, CCTV wall with click-to-inspect are all working. Create a detailed
implementation plan: list every file to create/modify, what each contains, and the build
order. Present the plan and wait for approval before writing code.
```
