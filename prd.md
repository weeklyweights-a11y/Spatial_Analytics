# Product Requirements Document (PRD)
# SpatialScore — Real-Time Hackathon Intelligence Platform

**Version:** 1.0
**Author:** Bhargavi Nallapuneni
**Date:** June 2026
**Status:** Draft

---

## 1. PRODUCT OVERVIEW

SpatialScore is a real-time spatial intelligence platform that gives hackathon organizers complete visibility into what every participant is doing throughout the event. Using fixed CCTV cameras across multiple floors, the system tracks, identifies, and scores each participant based on their actual behavior — coding, collaborating, mentoring, presenting, networking. The entire system runs on a single Google Cloud GPU VM, with camera feeds relayed from the venue over the internet. All scoring and tracking data is visible only to organizers through a CCTV monitoring wall dashboard — organizers see live camera feeds with every person labeled, and click on any person directly in the video to see their score. Participants are not shown scores, rankings, or tracking data.

**One-line pitch:** A CCTV command center where you see every participant labeled and scored in real time — click on anyone in the video to see exactly what they've contributed.

**Scale:** 1,000 participants across 3 floors (ground, 1st, 2nd), 10-13 fixed CCTV cameras, 24-hour hackathon.

**Infrastructure:** Single GCP GPU VM (NVIDIA L4). No on-premise hardware beyond cameras and a relay laptop.

---

## 2. PROBLEM STATEMENT

### 2.1 The Current State (Broken)

Hackathons today are measured entirely by output — a final demo judged by a panel in 3 minutes. This model is broken in five ways:

**For Participants:**
- A participant who mentors 5 teams, debugs critical blockers for others, and drives cross-team collaboration gets zero credit if their own demo isn't polished
- A freeloader who contributes nothing but stands on stage with their team receives the same "participant" credential
- Participants leave with a generic certificate that tells recruiters and VCs nothing about what kind of builder they are

**For Organizers:**
- Zero visibility into what's actually happening during the 12-24 hours of the hackathon
- No data on crowd flow, energy patterns, collaboration density, or dead zones
- No ability to intervene in real-time (send food to the busy area, send mentors to struggling teams)
- Post-event reports are based on guesswork and surveys, not observed behavior

**For Sponsors:**
- Sponsors pay $5K-$50K for booths but receive zero engagement analytics
- No data on how many participants visited their booth, how long they stayed, or whether they actually engaged
- ROI justification is "it felt good" — not defensible for budget approval

**For Recruiters / VCs (Match Day):**
- At Buildathon Dallas's Match Day, startups and VCs want to identify the best builders
- Resumes and final demos are noisy signals — they don't reveal work ethic, collaboration skills, mentoring ability, or resilience under pressure
- The real signal is behavioral: who grinded through the night, who helped others, who rallied their team when things broke

### 2.2 The Root Cause

There is no observability layer for physical hackathon behavior. Digital activity (git commits, Slack messages) captures a fraction of contribution. Physical behavior — collaborating in person, mentoring at a whiteboard, presenting impromptu demos, networking with sponsors — is invisible.

### 2.3 What We're Building

A passive, non-intrusive, camera-based system that watches everything and scores everyone — continuously, fairly, and transparently.

---

## 3. USER PERSONAS

### 3.1 Primary User: Organizer

**Name:** Bhargavi, hackathon organizer (Buildathon Dallas)
**Goal:** See exactly what every participant is doing in real time and score them based on actual contribution
**Pain:** During the event she's running blind — no idea who's actually coding, who's freeloading, which zones are dead, whether sponsors are getting traffic. After the event, judging is based on a 3-minute demo that doesn't reflect 12 hours of work
**What she wants from SpatialScore:** A command center where she can look up any participant by name and instantly see: where they are right now, what they're doing, their score, their full activity history. Plus a bird's-eye view of the entire venue — heatmaps, zone utilization, energy levels

### 3.2 Secondary User: Sponsor

**Name:** Jake, DevRel at an AI startup
**Goal:** Justify the $15K booth sponsorship to his VP
**Pain:** After the hackathon he has nothing but photos and a vague sense that "people came by"
**What he wants from SpatialScore:** A report from the organizers showing: 247 unique visitors to our booth, average dwell time 4.2 minutes, 38 returned for a second visit, peak traffic at 2PM

*Note: Sponsors don't access the system directly. Organizers generate and share sponsor reports.*

### 3.3 The Participant (Tracked, Not a User)

Participants are tracked but never see the system. They register at check-in (face capture for identification), consent to being tracked, and that's their only interaction with SpatialScore. They don't see scores, rankings, or any tracking data. The organizer uses this data internally for judging, awards, operational decisions, and sponsor reporting.

---

## 4. CORE FEATURES

### 4.1 Participant Registration + Identity Enrollment

**What:** During hackathon check-in, each participant shows a physical ID. The system captures their face, generates a face embedding, and links it to their profile.

**Flow:**
1. Participant arrives at registration — **multiple parallel stations** (4-5 tablets/laptops)
2. Registration staff opens the SpatialScore registration app
3. Participant shows physical ID → camera captures face
4. System detects face, generates 512-dim ArcFace embedding
5. Staff enters: name, team, track, skills, contact info
6. Embedding queued for FAISS index addition (write lock ensures one embedding added at a time across all stations — each add takes <1ms so no noticeable delay)
7. Participant receives standard hackathon badge (no SpatialScore branding needed)
8. Staff confirms consent verbally + checkbox in system
9. Participant walks away — they never interact with SpatialScore again
10. Participant is now trackable across all cameras on all floors

**Privacy consent:** During registration, participants are informed that cameras will track location and activities for event operations. Clear signage throughout venue. Opt-out available at any time (removes face embedding from index, person becomes anonymous in tracking).

### 4.2 Real-Time Multi-Camera Person Tracking

**What:** Every CCTV camera continuously identifies who is where across all 3 floors.

**How it works:**
- 10-13 fixed CCTV cameras cover defined zones across ground floor, 1st floor, and 2nd floor
- Camera feeds are relayed from the venue to a GCP GPU VM via ffmpeg (RTMP) over the internet
- On the VM, each camera feed is processed at 5-10 FPS
- Per frame: detect faces → compute embeddings → match against FAISS index → identify person
- Simultaneously: DEIMv2-wholebody49 detects body + extracts 49 keypoints (17 body + 6 feet + 26 hands) per person
- Roboflow supervision's ByteTrack maintains person IDs across consecutive frames
- Cross-camera re-identification: face embedding matching reconnects identity when a person moves between floors or camera views

**Output per frame:**
```
{
  participant_id: "P-0042",
  name: "Riya Sharma",
  camera_id: "CAM-03",
  zone: "coding_zone_a",
  bbox: [x1, y1, x2, y2],
  keypoints: [[x,y,conf], ...],  // 17 body landmarks
  timestamp: "2026-07-15T02:34:12Z",
  confidence: 0.94
}
```

### 4.3 Zone Definition + Management

**What:** The venue is divided into named zones, each mapped to camera views.

**Zones for Buildathon Dallas (across 3 floors):**

*Ground Floor:*
- Coding Zone A, B (main hacking areas)
- Registration Desk
- Food Area

*1st Floor:*
- Coding Zone C, D
- Demo Stage (presentation area)
- Mentor Booth (mentoring stations)

*2nd Floor:*
- Networking Lounge
- Sponsor Booths (one per sponsor: Lovable, TinyFish, Tavily, etc.)
- Rest Area

*Note: Exact zone layout will be finalized after venue walkthrough. Camera placement drives zone definitions — each zone must be covered by at least one camera.*

**How zones are defined:**
- Before the event, organizer draws polygons on each camera's view in the admin UI
- Each polygon is labeled with a zone name
- At runtime, person's bounding box centroid is tested against zone polygons → determines which zone they're in

### 4.4 Activity Classification

**What:** For each tracked person, classify what they're doing.

**Activity categories:**
| Activity | How Detected | Score Weight |
|----------|-------------|-------------|
| Coding | In coding zone + sitting + hands forward (laptop posture) | 1.0x |
| Collaborating | 2+ identified people within 1.5m in coding zone, facing each other | 1.5x |
| Mentoring | In mentor booth zone OR identified person moving between multiple teams' tables | 2.0x |
| Presenting | On demo stage zone + standing + facing audience direction | 2.0x |
| Networking | In networking lounge OR sponsor booth + standing + facing another person | 1.2x |
| Sponsor Engagement | In a specific sponsor's booth zone + dwell time > 2 min | 1.0x |
| Eating/Resting | In food area or rest area | 0x (neutral, doesn't penalize) |
| Idle/Wandering | In any zone + walking without stopping for > 3 min | 0x (neutral) |
| Helping Others | Person from Team A detected in Team B's coding area for > 10 min | 1.8x |

**Two-tier classification:**
- Tier 1 (MVP): Zone-based only. If you're in the coding zone, you're coding. Simple, reliable, no ML model needed.
- Tier 2 (Post-MVP): Zone + pose. YOLO keypoints fed into a classifier that distinguishes sitting-at-laptop from standing-in-group from presenting.

### 4.5 Personalized Scoring Engine

**What:** Every participant gets a continuously updating score based on their observed activities.

**Scoring formula:**
```
score(participant, t) = Σ (activity_weight × duration_minutes × zone_multiplier)
```

**Example for Riya over 12 hours:**
| Time Block | Zone | Activity | Duration | Weight | Points |
|-----------|------|----------|----------|--------|--------|
| 6PM-10PM | Coding Zone A | Coding | 240 min | 1.0 | 240 |
| 10PM-11PM | Team B's table | Helping Others | 60 min | 1.8 | 108 |
| 11PM-12AM | Mentor Booth | Mentoring | 60 min | 2.0 | 120 |
| 12AM-2AM | Coding Zone A | Collaborating | 120 min | 1.5 | 180 |
| 2AM-2:30AM | Food Area | Eating | 30 min | 0 | 0 |
| 2:30AM-5AM | Coding Zone A | Coding | 150 min | 1.0 | 150 |
| 5AM-6AM | Demo Stage | Presenting | 60 min | 2.0 | 120 |
| **TOTAL** | | | **720 min** | | **918 pts** |

**Behavioral Tags (auto-assigned based on activity distribution):**
- **Builder** — >50% time coding
- **Mentor** — >15% time mentoring or helping others
- **Collaborator** — >30% time collaborating
- **Networker** — >20% time in networking/sponsor zones
- **Solo Grinder** — >70% time coding alone
- **Presenter** — 3+ separate presenting sessions
- **Night Owl** — Active past 2AM
- **Cross-Pollinator** — Detected in 3+ different teams' coding areas

### 4.6 CCTV Monitoring Wall + Click-to-Inspect (Primary Dashboard)

**What:** The main dashboard is a live CCTV monitoring wall — a grid of all camera feeds showing every person labeled with bounding boxes. Organizers click directly on any person in the video to see their score card. No typing, no searching — pure visual point-and-click.

**How it works:**
1. All 10-13 camera feeds displayed in a tiled grid (ground floor, 1st floor, 2nd floor sections)
2. Every detected person has a bounding box drawn around them with their name above it
3. Boxes are color-coded by current activity: green (coding), blue (collaborating), orange (mentoring), purple (presenting), grey (idle)
4. Organizer clicks on any person's box in any camera feed
5. A score card pops up next to the clicked person showing:
   - Name, team, registration photo
   - Current activity and zone
   - Total score and rank out of 1,000
   - Mini radar chart (coding / collaborating / mentoring / presenting / networking)
   - Behavioral tags (Builder, Mentor, Night Owl, etc.)
   - "View Full Profile" button for detailed timeline
6. Click another person → card moves to them. Click empty space → card closes.

**Around the camera grid:**
- Venue heatmap (floor plan with zone occupancy overlays) — visible at a glance
- Live leaderboard (top participants, auto-updating)
- Energy graph (activity level over time)
- Alert notifications (zone at capacity, mentor booth empty, energy dip)

### 4.7 Organizer Command Center (Secondary Views)

**What:** Beyond the CCTV wall, the organizer has additional views accessible via navigation tabs.

**Leaderboard tab:**
- Full ranked list of all 1,000 participants
- Sortable by: total score, coding score, mentoring score, collaboration score
- Filterable by: team, track, floor, behavioral tag
- Compare mode: select 2-3 participants for side-by-side judging

**Heatmap tab:**
- Floor plan of each floor with zone occupancy overlays
- Toggle between floors (ground, 1st, 2nd)
- Real-time zone utilization bars
- Historical: scrub back in time to see how crowd patterns evolved

**Analytics tab:**
- Energy graph over time (when was the hackathon buzzing vs quiet)
- Zone utilization over time per floor
- Peak hours, dead hours

**Settings tab:**
- Camera management (URLs, status, zone polygon editor)
- Scoring weight configuration
- User account management

### 4.8 Sponsor Engagement Reports (Generated by Organizer)

**What:** Organizer generates per-sponsor engagement reports to share with sponsors post-event.

**Shows:**
- Unique visitors to their booth
- Average dwell time
- Return visitors (came back 2+ times)
- Peak traffic times
- Visitor breakdown by team/track
- Comparison vs other sponsor booths (anonymized)
- Exportable PDF report for sponsor's internal stakeholders

**Note:** Sponsors do not have direct access to the platform. The organizer reviews the data, generates the report, and shares it with each sponsor.

### 4.9 Judging + Awards Support

**What:** Organizers use SpatialScore data to inform judging decisions and awards beyond just the final demo.

**How:**
- Organizer pulls up the leaderboard sorted by total score, collaboration score, mentoring score, etc.
- "Best Collaborator" award → sort by collaborating_minutes + helping_minutes
- "Most Dedicated Builder" → sort by total coding hours
- "Community Champion" → sort by mentoring + cross-team visits
- During demo judging, organizer can cross-reference: "This team's demo crashed, but their builder coded 10 hours and mentored 3 teams — factor that in"
- If used with Match Day, organizer can selectively share anonymized behavioral insights with recruiting partners (with participant consent obtained separately)

---

## 5. SCORING PHILOSOPHY

### 5.1 Principles

1. **Contribution > Output.** We score what participants did, not what they shipped. A crashed demo doesn't erase 12 hours of mentoring.
2. **Collaboration > Competition.** Helping others scores higher than solo grinding. The organizer values community builders.
3. **Organizer discretion.** Scores are a tool for the organizer, not a public ranking. The organizer decides how to use the data — for awards, judging context, operational decisions, or sponsor reports.
4. **Fairness.** Resting and eating are neutral (0x), not negative. The system doesn't penalize human needs.
5. **Privacy first.** Participants consent to tracking but don't see the output. Raw video is never stored. Data is used for event operations only.

### 5.2 Anti-Gaming

Since participants don't see their scores or know the scoring formula, deliberate gaming is unlikely. However, the system still handles edge cases:
- **Person sits in mentor booth but is actually on their phone:** Pose classification (Phase 2) detects idle posture vs active engagement
- **Minimum dwell time:** 2 min required per zone visit to count — passing through doesn't score
- **Identity verification is biometric:** Face embedding match prevents impersonation

---

## 6. SUCCESS METRICS

| Metric | Target | How Measured |
|--------|--------|-------------|
| Registration-to-tracking success rate | >95% of registered participants tracked within 30 min | FAISS match rate |
| Activity classification accuracy | >85% (zone-based), >75% (pose-based) | Manual validation sample of 100 classifications |
| Organizer actionability | 5+ operational decisions made using real-time data during event | Organizer self-report |
| Sponsor report usefulness | >90% of sponsors say reports were "useful" or "very useful" | Post-event sponsor survey |
| System uptime during event | 99.5% (no more than 3 min downtime in 12 hours) | System monitoring |
| Dashboard latency | <5 seconds from physical action to dashboard update | End-to-end latency measurement |
| Participant lookup speed | <2 seconds to pull any participant's full profile | UI response time |
| Judging data usage | Organizer references SpatialScore data in 50%+ of judging decisions | Organizer self-report |

---

## 7. SCOPE + PHASING

### Phase 1: MVP for Buildathon Dallas

- Registration with face enrollment (parallel stations, 4-5 tablets)
- 10-13 fixed CCTV cameras across 3 floors
- Video relay from venue (ffmpeg on laptop → RTMP → GCP VM)
- Zone-based activity classification only (no pose classification)
- Basic scoring with time-in-zone weights
- CCTV monitoring wall dashboard with click-to-inspect score cards
- Heatmap, leaderboard, energy graph, alerts
- Sponsor engagement tracking
- Single GCP GPU VM (g2-standard-8, NVIDIA L4)

### Phase 2: Post-Dallas Enhancement

- Pose-based activity classification (YOLO keypoints → activity classifier)
- Sponsor engagement PDF report generation
- Cross-team collaboration detection ("helping others")
- Advanced filtering: "show me everyone who mentored for 2+ hours"
- Judging support: side-by-side team comparison views
- Person appearance-based Re-ID fallback (PersonViT) for when face isn't visible

### Phase 3: Platform + Enterprise

- Multi-event support (reusable across hackathons)
- NVIDIA DeepStream upgrade for 50+ camera deployments
- Robotics training data export (OpenTraj format)
- Digital twin visualization of venue
- SaaS model for other hackathon organizers
- Optional: participant opt-in data sharing for Match Day (separate consent flow)

---

## 8. RISKS + MITIGATIONS

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Privacy backlash | High | Explicit opt-in, clear signage, no raw video storage, GDPR/CCPA compliance, easy opt-out |
| Face recognition fails in low light | Medium | Infrared cameras for night hours, fallback to badge-based zone tracking |
| GPU hardware not available at venue | High | Reserve cloud GPU (AWS g5) as backup, test RTSP streaming latency beforehand |
| Scoring perceived as unfair | Medium | Transparent formula, post-event feedback loop, configurable weights |
| Participants game the system | Low | Anti-gaming rules (dwell time minimums, pose validation in Phase 2) |
| Drone regulations at venue | Medium | Verify indoor drone rules, have tethered drone backup, ensure venue insurance |

---

## 9. PRIVACY + ETHICS

**Data Collection:**
- Face embeddings (512-dim vectors) are stored, not raw face images
- Raw video frames are processed in memory and immediately discarded
- No audio is captured
- No personal conversations are monitored — only physical location and posture

**Consent:**
- Opt-in during registration with clear explanation of what's tracked
- Participants can opt out at any time — their embedding is deleted from FAISS, they become anonymous
- Minors (under 18) require guardian consent

**Data Retention:**
- Face embeddings: deleted 48 hours after event
- Activity logs: anonymized after 30 days (participant_id replaced with random hash)
- Aggregate analytics (heatmaps, zone stats): retained indefinitely (no PII)
- Participant profiles: retained only if participant opts in for Match Day / portfolio

**Transparency:**
- Participants are informed during registration that cameras track location and activity for event operations
- Signage throughout venue states cameras are active
- Scoring methodology is internal to the organizer team — not shared publicly
- Participants can request to know what data was collected about them (GDPR right of access)
- Participants can request deletion at any time (right to be forgotten)

---

*End of PRD*
