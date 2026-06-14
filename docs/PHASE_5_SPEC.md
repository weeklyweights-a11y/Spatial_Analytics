# Phase 5: Sponsors + Judging + Export

## What This Phase Does

Track sponsor booth engagement with granular in/out counting, generate polished PDF reports for sponsors, build the full participant profile page with complete activity timeline, and add data export capabilities for post-event analysis and robotics training data. By the end of this phase, the organizer can hand each sponsor a professional PDF showing exactly how many people visited their booth, how long they stayed, and when traffic peaked. The organizer can also export all participant scores as CSV and all trajectory data in OpenTraj format for robotics research.

This phase turns SpatialScore from a live monitoring tool into a complete event intelligence platform with deliverables.

## Prerequisites

- Phase 4 complete and all acceptance criteria passing
- Heatmap, analytics, alerts, enhanced leaderboard all working
- Zone polygon editor functional (zones can be created via UI)
- At least 2 sponsor booth zones defined in zones.yaml or via the zone editor

---

## Resources to Download + Install (Phase 5 additions)

### Model Weights

No new model downloads.

### Python Libraries

`weasyprint` was already added to requirements.txt in Phase 3. If not:
```
# Add to backend/requirements.txt
weasyprint>=61.0            # HTML-to-PDF rendering for sponsor reports
```

WeasyPrint requires system dependencies in the Docker image:
```dockerfile
# Add to backend/Dockerfile
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
    libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*
```

### npm Packages

```json
{
  "dependencies": {
    "@react-pdf/renderer": "^3.4"
  }
}
```

Alternative: generate PDFs server-side with WeasyPrint (recommended — keeps PDF logic in Python, avoids client-side rendering issues). If server-side, no new npm package needed.

### Code Patterns

**From [roboflow/supervision](https://github.com/roboflow/supervision) — sv.LineZone:**
- Documentation: https://supervision.roboflow.com/latest/how_to/track_objects/#linezone
- Pattern: define a line (start point, end point) across the sponsor booth entrance
- `line.trigger(detections)` returns two boolean masks: `crossed_in` (entered) and `crossed_out` (exited)
- We already use sv.PolygonZone for zone occupancy — LineZone adds directional in/out counting

**From [crowdbotp/OpenTraj](https://github.com/crowdbotp/OpenTraj):**
- Study their data format standard for trajectory datasets
- ETH/UCY format: `frame_id pedestrian_id pos_x pos_y` (tab-separated, one row per detection per frame)
- Our export follows this schema with additional columns: activity, zone
- This makes our data directly usable by trajectory prediction models (Social-LSTM, Trajectron++, AgentFormer)

**PDF report design — no specific repo:**
- Approach: build HTML template with Jinja2 → render to PDF with WeasyPrint
- Template includes: sponsor logo, key metrics cards, traffic chart (rendered as embedded SVG or base64 PNG), visitor breakdown table
- WeasyPrint handles CSS → PDF layout including page breaks, headers, footers

### Docker Images

No new Docker images.

---

## Section 1: Sponsor Booth Entry/Exit Tracking with sv.LineZone

### What to build

Add sv.LineZone to camera workers for each sponsor booth zone. This gives directional counting — not just "how many people are in the zone" (PolygonZone does that) but "how many people entered and exited, and when."

**Configuration — add line definitions to zones.yaml:**
```yaml
sponsor_lines:
  - name: "Lovable Booth Entrance"
    camera_id: "CAM-10"
    sponsor_name: "Lovable"
    start: [200, 250]    # line start point in camera-frame pixels
    end: [200, 50]       # line end point
    # Direction: crossing from left to right = "in", right to left = "out"
    # The direction is determined by which side of the line the detection crosses from
```

**Camera worker update:**
- In the camera worker (Phase 2), after PolygonZone processing, add LineZone processing:
  ```python
  for line_name, line_zone in self.sponsor_lines.items():
      crossed_in, crossed_out = line_zone.trigger(detections)
      
      for i, entered in enumerate(crossed_in):
          if entered:
              track_id = detections.tracker_id[i]
              participant_id = self.track_to_identity.get(track_id)
              if participant_id:
                  event = {
                      "type": "sponsor_entry",
                      "participant_id": participant_id,
                      "sponsor_name": line_name.sponsor_name,
                      "camera_id": self.camera_id,
                      "timestamp": datetime.utcnow().isoformat()
                  }
                  self.redis.xadd("sponsor_stream", event)
      
      for i, exited in enumerate(crossed_out):
          if exited:
              # Similar event with type "sponsor_exit"
  ```

**Sponsor event stream:** Separate Redis Stream `sponsor_stream` for sponsor entry/exit events. The scoring worker (or a dedicated sponsor aggregation worker) consumes these and updates the sponsor_engagement table.

**Sponsor engagement aggregation:** Add to the scoring worker's flush cycle (or create a separate lightweight worker):
- Consume `sponsor_stream` events
- For each sponsor, per hour bucket:
  - Count unique participant_ids who entered → unique_visitors
  - Count total entries → total_visits
  - Calculate avg dwell time: for each participant, time between entry and exit events → average
  - Count participants who entered more than once → return_visitors
- Upsert into sponsor_engagement table

---

## Section 2: Sponsor Visit Tracking per Participant

### What to build

Track which sponsors each participant visited, for how long, and how many times. This data appears in the participant's full profile and feeds into the sponsor reports.

**New table — participant_sponsor_visits:**
```sql
CREATE TABLE participant_sponsor_visits (
    id BIGSERIAL PRIMARY KEY,
    participant_id UUID NOT NULL REFERENCES participants(id),
    sponsor_id UUID NOT NULL REFERENCES sponsors(id),
    entered_at TIMESTAMP WITH TIME ZONE NOT NULL,
    exited_at TIMESTAMP WITH TIME ZONE,
    dwell_seconds INTEGER,
    visit_number INTEGER DEFAULT 1    -- 1st visit, 2nd visit, etc.
);

CREATE INDEX idx_sponsor_visits_participant ON participant_sponsor_visits(participant_id);
CREATE INDEX idx_sponsor_visits_sponsor ON participant_sponsor_visits(sponsor_id, entered_at);
```

**Tracking logic:** When a participant crosses a sponsor LineZone "in", create a new row with `entered_at` set and `exited_at` NULL. When they cross "out", update the most recent unexited row with `exited_at` and calculate `dwell_seconds`. If they never cross "out" (left the camera view another way), close the visit after 30 minutes of no activity in that zone.

---

## Section 3: Sponsor Report API

### What to build

**GET /api/v1/sponsors/{id}/report**
- Returns comprehensive engagement data for a single sponsor
- Response:
  ```json
  {
    "data": {
      "sponsor": {"id": "uuid", "name": "Lovable", "tier": "gold"},
      "metrics": {
        "unique_visitors": 247,
        "total_visits": 312,
        "avg_dwell_seconds": 252,
        "median_dwell_seconds": 180,
        "return_visitors": 38,
        "return_rate_pct": 15.4,
        "peak_hour": "14:00",
        "total_dwell_minutes": 1042
      },
      "hourly_traffic": [
        {"hour": "18:00", "visitors": 12, "entries": 15},
        {"hour": "19:00", "visitors": 28, "entries": 34},
        ...
      ],
      "visitor_breakdown": {
        "by_track": {"ai_ml": 104, "web3": 57, "devtools": 44, "other": 42},
        "by_floor": {"ground": 89, "first": 95, "second": 63}
      },
      "top_visitors": [
        {"participant_id": "uuid", "name": "Riya Sharma", "visits": 3, "total_dwell_minutes": 18}
      ]
    }
  }
  ```
- Source: sponsor_engagement table + participant_sponsor_visits table + participants table JOINs
- Auth: admin, operator

**GET /api/v1/sponsors/{id}/report/pdf**
- Returns the same data rendered as a downloadable PDF
- Content-Type: application/pdf
- Content-Disposition: attachment; filename="spatialscore_lovable_report.pdf"
- Auth: admin

---

## Section 4: PDF Report Generation

### What to build

Server-side PDF generation using Jinja2 HTML templates + WeasyPrint.

**Template: `backend/templates/sponsor_report.html`**

The HTML template is a single-page professional report. Design:
- Header: SpatialScore logo + sponsor logo + event name + date
- Key metrics cards row: Unique Visitors, Avg Dwell Time, Return Rate, Peak Hour (4 cards in a row)
- Traffic chart: hourly visitor count as a bar chart. Since WeasyPrint can't run JavaScript, render the chart as an SVG generated server-side using matplotlib or a lightweight SVG chart library. Embed as inline SVG in the HTML.
- Visitor breakdown: two side-by-side pie charts (by track, by team size) rendered as inline SVG
- Visitor table: top 10 visitors by dwell time with name, team, visits, total time
- Footer: "Generated by SpatialScore for Buildathon Dallas — {date}"

**PDF generation endpoint flow:**
1. Fetch sponsor report data (same as GET /sponsors/{id}/report)
2. Generate chart SVGs using matplotlib:
   - `fig, ax = plt.subplots(); ax.bar(hours, counts); buf = io.BytesIO(); fig.savefig(buf, format='svg')`
   - Convert to base64 or inline SVG string
3. Render Jinja2 template with data + chart SVGs
4. Convert HTML to PDF: `weasyprint.HTML(string=html).write_pdf()`
5. Return PDF as StreamingResponse

**PDF styling:**
- A4 page size
- Clean, professional design (no flashy colors — this goes to sponsor's VP)
- CSS embedded in the template (WeasyPrint supports CSS paged media: @page rules, page breaks, headers/footers)

---

## Section 5: Sponsor Reports Dashboard Page

### What to build

`dashboard/src/pages/SponsorReports.tsx` — sponsor engagement dashboard for organizers.

**Layout:**
- Sponsor selector: list of all sponsors with their tier badges
- Click a sponsor → shows their report inline
- "Download PDF" button → calls GET /sponsors/{id}/report/pdf, triggers browser download

**Report view:**
- Key metrics cards: Unique Visitors, Avg Dwell, Return Rate, Peak Hour
- Traffic chart: Recharts BarChart showing hourly visitor count
- Visitor breakdown: Recharts PieChart for track distribution
- Top visitors table: name, team, visits, total dwell time
- Comparison section: "vs Other Sponsors" — bar chart comparing unique visitors across all sponsors (anonymized — each sponsor only sees their own detailed data, but the organizer sees all)

**Components:**
- `SponsorCard.tsx` — single sponsor's metric summary (used in sponsor list)
- `SponsorReport.tsx` — full inline report for one sponsor
- `TrafficChart.tsx` — Recharts BarChart for hourly traffic
- `VisitorBreakdown.tsx` — Recharts PieChart for track/floor distribution

---

## Section 6: Enhanced Participant Profile Page

### What to build

Upgrade the Phase 3 participant profile page with full timeline detail and sponsor visit history.

**Additions to `dashboard/src/pages/ParticipantProfile.tsx`:**

**Complete activity timeline:**
- Vertical timeline with hour-by-hour blocks (already basic from Phase 3)
- Upgrade: each hour block expands to show sub-activities. E.g., "10PM-11PM: 35 min coding, 15 min collaborating, 10 min idle"
- Color-coded bars within each hour block showing activity distribution
- Scrollable, covering the entire event duration

**Sponsor visits section:**
- List of sponsor booths visited with: sponsor name, number of visits, total dwell time, timestamps
- "Riya visited Lovable 3 times for a total of 18 minutes. First visit: 8:15 PM (4 min). Second visit: 10:30 PM (6 min). Third visit: 1:20 AM (8 min)."

**Teams/zones visited section:**
- List of unique zones visited (beyond their own team's coding zone)
- "Visited 4 teams' coding areas" — relevant for Cross-Pollinator tag
- Time spent on each floor: ground (6h), 1st (4h), 2nd (2h)

**API additions:**

**GET /api/v1/participants/{id}/sponsor-visits**
- Returns list of sponsor visits for this participant
- Source: participant_sponsor_visits table

**GET /api/v1/participants/{id}/zone-history**
- Returns unique zones visited with time spent in each
- Source: activity_logs table, grouped by zone

---

## Section 7: Data Export

### What to build

Export endpoints for post-event data analysis.

**GET /api/v1/export/scores**
- Returns CSV of all participants with score breakdowns
- Content-Type: text/csv
- Content-Disposition: attachment; filename="spatialscore_scores_{date}.csv"
- Columns: participant_id, name, team_name, track, total_score, rank, coding_minutes, collaborating_minutes, mentoring_minutes, presenting_minutes, networking_minutes, helping_minutes, idle_minutes, tags, registered_at, last_seen_at
- Source: participants JOIN scores
- Auth: admin only
- Rate limit: 5/minute (expensive query)

**GET /api/v1/export/activity-logs**
- Returns CSV of all activity log events
- Query params: `?participant_id=uuid` (optional — export for one participant or all)
- Content-Type: text/csv
- Columns: timestamp, participant_id, name, camera_id, zone, activity, confidence
- Source: activity_logs JOIN participants
- Warning: this can be ~9 million rows for the full event. Stream the response — don't load into memory.
- Auth: admin only
- Rate limit: 2/minute

**GET /api/v1/export/trajectories**
- Returns trajectory data in OpenTraj-compatible format for robotics training
- Query params: `?format=opentraj|json`
- OpenTraj format (TSV):
  ```
  frame_id	pedestrian_id	pos_x	pos_y	activity	zone
  1	abc-123	245.5	182.3	coding	Coding Zone A
  2	abc-123	245.8	182.1	coding	Coding Zone A
  ```
- frame_id: sequential frame number across the entire event
- pedestrian_id: participant UUID (or anonymized hash if export is for public sharing)
- pos_x, pos_y: bounding box centroid coordinates in camera frame (or floor plan coordinates if calibrated)
- activity: the classified activity at that frame
- zone: the zone the participant was in
- Source: activity_logs table, extracting position from bbox JSONB field
- Auth: admin only
- Rate limit: 2/minute
- Note on anonymization: include query param `?anonymize=true` to replace participant_ids with SHA256 hashes and omit names. For sharing trajectory data externally.

**Streaming large exports:** Use FastAPI's StreamingResponse with a generator that yields CSV rows in chunks:
```python
async def generate_csv():
    yield header_row
    async for batch in db.stream(query, batch_size=1000):
        for row in batch:
            yield format_csv_row(row)

return StreamingResponse(generate_csv(), media_type="text/csv")
```

---

## Section 8: Export UI in Dashboard

### What to build

Add export buttons to relevant dashboard pages.

**Leaderboard page:**
- "Export Scores CSV" button in the top bar → triggers GET /export/scores download
- Only visible to admin role

**Settings page — new "Export" tab:**
- Three export cards:
  - "Participant Scores" — download scores CSV, shows estimated file size
  - "Activity Logs" — download full activity logs CSV, warning: "~9M rows, may take a minute"
  - "Trajectory Data" — download OpenTraj format, with anonymization toggle checkbox
- Each card has a "Download" button that triggers the corresponding export endpoint
- Show download progress (Content-Length header → progress bar in browser)

---

## Section 9: Database Changes

### What to build

Alembic migration for Phase 5 additions.

**New table — participant_sponsor_visits** (as defined in Section 2)

**Update sponsor_engagement table** — add columns if missing:
```sql
ALTER TABLE sponsor_engagement ADD COLUMN IF NOT EXISTS median_dwell_seconds FLOAT DEFAULT 0;
ALTER TABLE sponsor_engagement ADD COLUMN IF NOT EXISTS peak_visitors_in_hour INTEGER DEFAULT 0;
```

---

## Section 10: Logging + Error Handling

### What to build

**Sponsor tracking logs:**
- `INFO` on sponsor entry: "Sponsor entry: participant={name}, sponsor={sponsor_name}, camera={cam_id}"
- `INFO` on sponsor exit: "Sponsor exit: participant={name}, sponsor={sponsor_name}, dwell={seconds}s"
- `WARNING` on unclosed visit (>30 min without exit): "Unclosed sponsor visit: participant={name}, sponsor={sponsor_name}, entered_at={time} — auto-closing"

**Export logs:**
- `INFO` on export start: "Export started: type={scores|activity_logs|trajectories}, user={username}, format={csv|opentraj}"
- `INFO` on export complete: "Export complete: type={type}, rows={count}, duration={seconds}s, size={mb}MB"
- `ERROR` on export failure: "Export failed: type={type}, error={error}"

**PDF generation logs:**
- `INFO` on PDF generation: "Sponsor PDF generated: sponsor={name}, pages=1, size={kb}KB"
- `ERROR` on PDF failure: "Sponsor PDF generation failed: sponsor={name}, error={error}"

**Error handling for exports:**
- If PostgreSQL connection drops mid-export: return partial data with a header indicating incompleteness, log error
- If export takes >5 minutes: timeout and return 504 with message "Export timed out. Try filtering to a smaller dataset."

---

## Section 11: Security for Exports

### What to build

Exports contain PII (participant names, activity data). Additional security:

- All export endpoints require admin role (not operator or viewer)
- Export responses include `Cache-Control: no-store` header — browser doesn't cache the CSV
- Export audit log: every export is logged with: who exported, what type, when, whether anonymized. Store in a simple `export_log` table or just structured log entries.
- Anonymization option: `?anonymize=true` replaces participant_ids with SHA256 hashes, removes names and emails from the export. For sharing data externally (robotics researchers, publications).

**Rate limiting:**
```python
@app.get("/api/v1/export/scores")
@limiter.limit("5/minute")

@app.get("/api/v1/export/activity-logs")
@limiter.limit("2/minute")

@app.get("/api/v1/export/trajectories")
@limiter.limit("2/minute")

@app.get("/api/v1/sponsors/{id}/report/pdf")
@limiter.limit("10/minute")
```

---

## Section 12: Tests for Phase 5

### What to build

**Unit tests:**
- `tests/unit/test_sponsor_aggregation.py`:
  - Given 5 entry + 5 exit events for sponsor A, verify unique_visitors, total_visits, avg_dwell
  - Given 3 entries from same participant, verify return_visitors = 1
  - Given entry without exit after 30 min, verify visit is auto-closed

- `tests/unit/test_trajectory_export.py`:
  - Given activity logs with bbox data, verify OpenTraj format output matches expected schema
  - Given anonymize=true, verify participant_ids are hashed and names are omitted

- `tests/unit/test_pdf_generation.py`:
  - Given sponsor report data, verify HTML template renders without errors
  - Verify WeasyPrint converts HTML to PDF (check output is valid PDF bytes starting with %PDF)

**Integration tests:**
- `tests/integration/test_sponsor_pipeline.py`:
  - Simulate sponsor entry/exit events in Redis sponsor_stream
  - Run aggregation, verify sponsor_engagement table updated correctly
  - GET /sponsors/{id}/report returns correct metrics

- `tests/integration/test_exports.py`:
  - Seed 10 participants with scores, GET /export/scores → verify CSV has 10 rows with correct columns
  - GET /export/trajectories?format=opentraj → verify TSV format matches OpenTraj schema
  - GET /export/trajectories?anonymize=true → verify no real names or UUIDs in output

- `tests/integration/test_sponsor_pdf.py`:
  - GET /sponsors/{id}/report/pdf → verify response is application/pdf, size > 0

---

## What NOT to Build in This Phase

- No load testing (Phase 6)
- No venue-specific setup or configuration (Phase 6)
- No ffmpeg relay testing (Phase 6)
- No runbook or operational documentation (Phase 6)
- No demo data seeding (Phase 6)
- No automated camera-to-floor-plan coordinate calibration

---

## Acceptance Criteria

**Sponsor Tracking:**
- [ ] sv.LineZone configured for at least one sponsor booth entrance
- [ ] Sponsor entry/exit events appear in Redis sponsor_stream when a tracked person crosses the line
- [ ] Sponsor engagement table updates with unique_visitors, total_visits, avg_dwell_seconds per hour
- [ ] participant_sponsor_visits table records individual visits with entry/exit timestamps and dwell time
- [ ] Unclosed visits (entry without exit for 30+ min) are automatically closed

**Sponsor Reports:**
- [ ] GET /sponsors/{id}/report returns comprehensive engagement data including hourly traffic and visitor breakdown
- [ ] GET /sponsors/{id}/report/pdf returns a valid PDF file
- [ ] PDF contains: sponsor name, key metrics, traffic chart, visitor breakdown, top visitors table
- [ ] Sponsor reports dashboard page shows all sponsors with inline report view
- [ ] "Download PDF" button triggers browser download of the PDF

**Participant Profile:**
- [ ] Participant profile page shows expanded hour-by-hour activity timeline with sub-activity breakdowns
- [ ] Sponsor visits section shows which booths the participant visited, how many times, and total dwell time
- [ ] Zone history section shows all unique zones visited
- [ ] GET /participants/{id}/sponsor-visits returns visit data
- [ ] GET /participants/{id}/zone-history returns zone visit data

**Data Export:**
- [ ] GET /export/scores returns valid CSV with all 1,000 participants and correct columns
- [ ] GET /export/activity-logs streams CSV without loading all rows into memory
- [ ] GET /export/trajectories with format=opentraj returns valid TSV in OpenTraj schema
- [ ] GET /export/trajectories?anonymize=true contains no real names or UUIDs
- [ ] Export endpoints require admin role — operator and viewer get 403
- [ ] Export buttons visible only to admin role in dashboard

**Infrastructure:**
- [ ] WeasyPrint renders PDFs correctly in Docker container (system dependencies installed)
- [ ] Rate limiting applied to all export endpoints
- [ ] All new unit and integration tests pass

---

## How to Give This to Cursor

```
Read .cursorrules, PROJECT.md, and docs/PHASE_5_SPEC.md. This is Phase 5 of SpatialScore.
Phases 1-4 are complete — registration, camera pipeline, scoring, CCTV wall, heatmap,
analytics, alerts, and enhanced leaderboard are all working. Create a detailed
implementation plan: list every file to create/modify, what each contains, and the build
order. Present the plan and wait for approval before writing code.
```
