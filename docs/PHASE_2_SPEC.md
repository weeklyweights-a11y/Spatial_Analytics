# Phase 2: Camera Pipeline + Identity

## What This Phase Does

Make the system see. Camera workers process live video streams from MediaMTX, detect every person using DEIMv2-wholebody49 (49 keypoints), track them across frames with supervision ByteTrack, identify them by face using the SCRFD + ArcFace + FAISS pipeline from Phase 1, classify which zone they're in using supervision PolygonZone, determine their activity from zone type plus hand keypoint position, and emit structured activity events into Redis Stream. By the end of this phase, you can push test RTMP streams from your laptop to the GCP VM and see identified, tracked, zone-assigned, activity-classified people flowing as events in Redis — with annotated frames (bounding boxes, names, activity colors) ready for the CCTV wall in Phase 3.

This is the hardest phase. Every frame from every camera runs through 5 models/algorithms in sequence, all in real time. If this phase works, the rest is data presentation.

## Prerequisites

- Phase 1 complete and all acceptance criteria passing
- DEIMv2-wholebody49 ONNX model in models/ directory (exported from PyTorch checkpoint in Phase 1 setup)
- At least one test video or RTSP camera to push via ffmpeg for testing
- GCP VM running with GPU accessible via nvidia-smi

---

## Resources to Download + Install (Phase 2 additions)

### Model Weights

**DEIMv2-wholebody49** — should already be in models/ from Phase 1 setup. If not:
```bash
# Clone DEIMv2 repo
git clone https://github.com/Intellindust-AI-Lab/DEIMv2.git /tmp/deimv2
cd /tmp/deimv2

# Install DEIMv2 dependencies (in a temporary venv, not in the Docker image)
pip install -r requirements.txt

# Download pretrained checkpoint
# Check their README or HuggingFace for the wholebody49 weights
# Model page: https://github.com/Intellindust-AI-Lab/DEIMv2#model-zoo

# Export to ONNX
python tools/export_onnx.py \
  --config configs/deimv2_s_wholebody49.yml \
  --checkpoint weights/deimv2_s_wholebody49.pth \
  --output /path/to/spatialscore/models/deimv2_s_wholebody49.onnx

# Verify the ONNX model
python -c "
import onnxruntime as ort
sess = ort.InferenceSession('models/deimv2_s_wholebody49.onnx')
print('Input:', sess.get_inputs()[0].name, sess.get_inputs()[0].shape)
print('Outputs:', [o.name for o in sess.get_outputs()])
print('Model loaded successfully')
"
```

**If DEIMv2 wholebody49 ONNX export is not available or problematic:**

Fallback Option A — Use standard DEIMv2 for detection (boxes only) + RTMPose for keypoints:
```bash
# DEIMv2-S for person detection
# Export from their repo as above, but standard detection config (no wholebody)
# Result: models/deimv2_s_det.onnx

# RTMPose for 133 whole-body keypoints (take body+hands+feet = 49 from the 133)
# From: https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose
wget https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.pth
# Export to ONNX following mmpose docs
```

Fallback Option B — Use YOLO11-Pose temporarily (17 keypoints instead of 49):
```bash
pip install ultralytics
python -c "from ultralytics import YOLO; YOLO('yolo11n-pose.pt')"
# Note: this is a temporary fallback. The interface (boxes + keypoints arrays fed to sv.Detections) stays the same.
# The activity classifier will work with 17 keypoints but with less accuracy (no hand/feet detail).
# Replace with DEIMv2 wholebody49 as soon as the ONNX export is sorted.
```

**The key principle:** The person_detector.py wrapper always returns the same interface — `(boxes, scores, keypoints)` — regardless of which model is underneath. The rest of the pipeline (tracker, identity linker, zone classifier, activity classifier) doesn't care which model produced the detections. If keypoints has shape (N, 49, 3) the activity classifier uses hand positions. If keypoints has shape (N, 17, 3) it falls back to zone-only classification. Build the interface first, swap the model later.

### Python Libraries (additions to requirements.txt for Phase 2)

```
# Add to backend/requirements.txt

supervision>=0.28            # ByteTrack tracking, PolygonZone, LineZone, annotators, video processing
```

That's it — supervision is the only new pip dependency. ONNX Runtime, OpenCV, NumPy, FAISS are already installed from Phase 1.

Note: Do NOT install `ultralytics` unless using the YOLO fallback. Do NOT install `trackers` (roboflow/trackers) — supervision's built-in ByteTrack is sufficient for fixed CCTV cameras.

### Code Patterns Extracted from Open Source Repos

**From [roboflow/supervision](https://github.com/roboflow/supervision) — documentation, not source code:**
- Study their PolygonZone tutorial: https://supervision.roboflow.com/latest/how_to/detect_and_count_objects_in_zone/
- Study their ByteTrack integration: how to construct sv.Detections manually and pass to tracker
- Study their annotator examples: BoxAnnotator, LabelAnnotator, HeatMapAnnotator, TraceAnnotator
- Study sv.get_video_frames_generator for RTSP handling
- We use supervision as a library (pip install), not as source code to copy

**From [roboflow/notebooks](https://github.com/roboflow/notebooks):**
- Reference notebook: `how-to-detect-and-count-objects-in-polygon-zone.ipynb` — the zone counting pattern we follow
- Reference notebook: speed estimation with ByteTrack — the tracking + annotation pattern

**From [dronefreak/human-action-classification](https://github.com/dronefreak/human-action-classification):**
- Study their pose-based classification approach: how they convert keypoint coordinates to relative angles and distances for activity classification
- We don't use their models or training pipeline — just the concept of "keypoint positions → activity label"
- Specifically: how they determine "sitting" vs "standing" vs "moving" from shoulder-hip-knee angles
- Rewrite the relevant logic in our `backend/core/activity_classifier.py` adapted for 49 keypoints

**From [Intellindust-AI-Lab/DEIMv2](https://github.com/Intellindust-AI-Lab/DEIMv2):**
- Study their ONNX export script to understand input/output tensor names and shapes
- Study their inference example to understand preprocessing (resize, normalize, pad)
- Study their post-processing (NMS, confidence filtering) if not built into the model
- Rewrite as our `backend/core/person_detector.py`

### Test Videos (downloaded to VM for testing)

```bash
# Download a crowd/office video for testing
# Option A: Use yt-dlp to grab a public video of people working indoors
pip install yt-dlp
yt-dlp -f 'bestvideo[height<=1080]' -o test_data/test_video.mp4 "https://youtube.com/watch?v=XXXX"

# Option B: Record a short video of yourself + friends walking around, sitting, standing
# This is better because you can register your own faces for identity testing

# Store test videos in test_data/ (gitignored)
```

### Docker Images (no new images in Phase 2)

All Docker images from Phase 1 are reused. Camera worker containers use the same backend image — just a different command.

---

## Section 1: DEIMv2 Person Detector

### What to build

`backend/core/person_detector.py` — wrapper around the DEIMv2-wholebody49 ONNX model.

**Model loading:** Load `deimv2_s_wholebody49.onnx` via ONNX Runtime with CUDAExecutionProvider. Fall back to CPUExecutionProvider for dev/testing without GPU. The model is loaded ONCE when the camera worker process starts and stays in GPU memory for the entire event.

**Inference method:** `detect(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]`
- Input: BGR frame from OpenCV (H x W x 3, uint8)
- Preprocessing: resize to model input size, normalize pixel values, convert to float32, add batch dimension
- Output: `(boxes, scores, keypoints)` where:
  - `boxes`: (N, 4) float32 — xyxy format bounding boxes
  - `scores`: (N,) float32 — confidence scores
  - `keypoints`: (N, 49, 3) float32 — 49 keypoints, each with (x, y, confidence)
- Post-processing: apply confidence threshold (default 0.3), NMS if not built into the model

**Keypoint map (49 keypoints):**
```
Body (0-16): nose, left_eye, right_eye, left_ear, right_ear,
             left_shoulder, right_shoulder, left_elbow, right_elbow,
             left_wrist, right_wrist, left_hip, right_hip,
             left_knee, right_knee, left_ankle, right_ankle
Feet (17-22): left_big_toe, left_small_toe, left_heel,
              right_big_toe, right_small_toe, right_heel
Hands (23-48): left_hand (13 points), right_hand (13 points)
```

**Important:** If the exact DEIMv2 wholebody49 ONNX model is not available or the keypoint format differs, adapt the wrapper to match whatever the model actually outputs. The rest of the system only cares about `boxes`, `scores`, and `keypoints` arrays — it doesn't care about the model internals. Document the actual keypoint indices in a comment at the top of person_detector.py.

**Fallback:** If DEIMv2 ONNX export proves problematic, use the DEIMv2 PyTorch model directly with `torch.no_grad()` inference. ONNX is preferred for speed but not worth blocking the phase over. If the wholebody49 variant doesn't exist as a separate config, use standard DEIMv2 for person detection (boxes only) and add a separate lightweight pose model (e.g. RTMPose via ONNX) for keypoints. The interface to the rest of the system stays the same.

---

## Section 2: Supervision Integration

### What to build

`backend/core/person_tracker.py` — the bridge between DEIMv2 output and supervision's tracking/zone/annotation ecosystem.

**Tracker initialization:**
```python
tracker = sv.ByteTrack(
    track_activation_threshold=0.25,
    lost_track_buffer=30,        # keep lost tracks for 30 frames (3 seconds at 10 FPS)
    minimum_matching_threshold=0.8,
    frame_rate=10
)
smoother = sv.DetectionsSmoother(length=5)  # smooth over 5 frames to reduce flicker
```

**Detection conversion:** DEIMv2 outputs raw numpy arrays. Convert to supervision Detections:
```python
detections = sv.Detections(
    xyxy=boxes,           # (N, 4) bounding boxes
    confidence=scores,    # (N,) confidence scores
    data={"keypoints": keypoints}  # (N, 49, 3) keypoints stored in data dict
)
```

Do NOT use `sv.Detections.from_ultralytics()`. DEIMv2 is not an Ultralytics model. Construct Detections manually every time.

**Tracking:** Pass detections through ByteTrack on every frame:
```python
detections = tracker.update_with_detections(detections)
detections = smoother.update_with_detections(detections)
```

After tracking, each detection has a `tracker_id` in `detections.tracker_id` — a persistent integer ID that follows the person across frames.

**Zone detection:** Managed by the camera worker (Section 4), not this module.

---

## Section 3: Face-to-Track Identity Linking

### What to build

`backend/core/identity_linker.py` — links supervision track IDs to registered participant UUIDs using the face recognition pipeline from Phase 1.

**The problem:** ByteTrack gives each person a track_id (integer). The FAISS index maps face embeddings to participant_ids (UUIDs). We need to connect them: track_42 = participant "abc-123" = "Riya Sharma".

**The approach:** Every N frames (configurable, default every 20 frames = every 2 seconds at 10 FPS), run face detection on the full frame. For each detected face:
1. Run SCRFD → get face bounding box
2. Find which tracked person's body bounding box contains this face (IoU overlap or containment check)
3. Run ArcFace → get 512-dim embedding
4. Search FAISS → get participant_id if similarity > threshold (0.5)
5. Store mapping: `track_id → participant_id`

**Track-to-identity cache:** A dictionary `{track_id: participant_id}` maintained in memory. Once a track is identified, it stays identified until the track is lost (ByteTrack drops it after `lost_track_buffer` frames of not seeing the person). When the track reappears with a new track_id, the face will be re-detected and re-linked within 2 seconds.

**Face-to-body matching:** Given a face bounding box from SCRFD and a list of person bounding boxes from DEIMv2/ByteTrack, find which person "owns" this face. Use containment: the face bbox center should be inside the person bbox. If multiple person boxes contain the face center (unlikely but possible with overlapping people), pick the one with highest IoU between face bbox and person bbox upper region.

**Unidentified people:** If a tracked person has no face match after 10 seconds (5 face recognition cycles), they remain as `track_id` with `participant_id = None`. They still get bounding boxes and zone classification, but no name label and no scoring. They might be someone who didn't register, or whose face hasn't been visible to the camera yet.

**Thread safety:** The face recognition runs in the same process as the camera worker (not a separate thread). It's synchronous within the per-frame processing loop. The FAISS read (search) is thread-safe. The track-to-identity cache is process-local (each camera worker has its own cache). A person identified on CAM-01 needs to be re-identified when they appear on CAM-05 — the face recognition will match them to the same participant_id within 2 seconds.

---

## Section 4: Camera Worker Process

### What to build

`backend/workers/camera_worker.py` — the main processing loop for a single camera stream. One instance runs per camera, each as a separate process in Docker Compose.

**Process startup:**
1. Parse command-line args: `--camera-id CAM-01 --rtsp-url rtsp://mediamtx:8554/cam01`
2. Load DEIMv2 model into GPU memory (person_detector.py)
3. Load SCRFD + ArcFace models into GPU memory (face_detector.py, face_recognizer.py)
4. Load FAISS index from disk into RAM (face_matcher.py)
5. Load zone definitions from configs/zones.yaml — filter to zones assigned to this camera_id
6. Initialize supervision ByteTrack tracker
7. Initialize supervision PolygonZones from zone polygon coordinates
8. Initialize supervision annotators (BoxAnnotator, LabelAnnotator, HeatMapAnnotator, TraceAnnotator)
9. Connect to Redis
10. Start frame processing loop

**Frame processing loop:** Use `sv.get_video_frames_generator(rtsp_url)` to iterate over frames from the RTSP stream. Process at the native speed of the stream (the generator yields frames as they arrive). If processing is slower than the stream, frames will be dropped by the generator — this is acceptable.

**Per-frame pipeline (detailed):**

Step 1 — Person detection:
- Run DEIMv2 on the frame → boxes, scores, keypoints (49 per person)
- Construct sv.Detections manually
- Run ByteTrack → persistent track IDs
- Run DetectionsSmoother → reduce flicker

Step 2 — Face recognition (every 20 frames):
- Run SCRFD on the frame → face bounding boxes
- For each face, find the matching tracked person (containment check)
- Run ArcFace → 512-dim embedding
- Search FAISS → participant_id
- Update track-to-identity cache

Step 3 — Zone classification:
- For each zone configured for this camera, call `zone.trigger(detections)` → boolean mask
- Each tracked person gets assigned to the zone whose polygon contains their bbox centroid
- If a person is in no zone (between zones, in a hallway), assign zone "unassigned"
- Update zone occupancy in Redis: `HSET zone_occupancy {zone_name} {zone.current_count}`

Step 4 — Activity classification:
- `backend/core/activity_classifier.py` — takes zone_type and keypoints, returns activity string
- MVP logic (zone-based + hand heuristic):
  - If zone_type is "coding": check hand keypoint positions. Wrists (keypoints 9, 10) below shoulders (keypoints 5, 6) in y-axis AND within shoulder width in x-axis → "coding". Wrists far apart and moving (compare to previous frame) → "collaborating" (gesturing). Wrists in lap (below hips, keypoints 11, 12) → "idle"
  - If zone_type is "mentoring" → "mentoring"
  - If zone_type is "presenting" → "presenting"
  - If zone_type is "networking" → "networking"
  - If zone_type is "sponsor" → "sponsor_engagement"
  - If zone_type is "food" → "eating"
  - If zone_type is "rest" → "resting"
  - Default → "idle"
- The classifier stores previous frame's keypoints per track_id to detect motion (needed for distinguishing coding from idle)

Step 5 — Emit activity event:
- For each tracked person with a resolved participant_id:
  ```python
  event = {
      "participant_id": participant_id,
      "camera_id": camera_id,
      "zone": zone_name,
      "zone_type": zone_type,
      "activity": activity,
      "track_id": track_id,
      "bbox": [x1, y1, x2, y2],
      "confidence": float,
      "timestamp": datetime.utcnow().isoformat()
  }
  redis.xadd("activity_stream", event)
  ```

Step 6 — Generate annotated frame:
- Draw bounding boxes color-coded by activity: green (#22c55e) for coding, blue (#3b82f6) for collaborating, orange (#f97316) for mentoring, purple (#a855f7) for presenting, gray (#6b7280) for idle/eating/resting
- Draw name labels above each box (participant name if identified, "Unknown" if not)
- Draw zone boundary polygons as semi-transparent overlays
- Store the annotated frame in a shared buffer (for MJPEG streaming to dashboard in Phase 3)
- The annotated frame is NOT saved to disk — it's held in memory and overwritten every frame

**Stream reconnection:** If `sv.get_video_frames_generator` fails (RTSP stream drops), log a warning and retry with exponential backoff: 1s, 2s, 4s, 8s, 16s max. Keep retrying until the stream comes back. Log each reconnection attempt.

**Graceful shutdown:** On SIGTERM (Docker stop), flush any pending Redis events, save FAISS index to disk (if this worker modified it, which it shouldn't — only the API server modifies FAISS), log shutdown, exit cleanly.

---

## Section 5: Zone Configuration

### What to build

The zone system that maps physical venue areas to named zones in each camera's view.

**configs/zones.yaml format:**
```yaml
zones:
  - name: "Coding Zone A"
    type: "coding"
    camera_id: "CAM-01"
    floor: 0
    capacity: 50
    polygon: [[100, 50], [600, 50], [600, 400], [100, 400]]

  - name: "Mentor Booth"
    type: "mentoring"
    camera_id: "CAM-06"
    floor: 1
    capacity: 10
    polygon: [[200, 100], [500, 100], [500, 350], [200, 350]]

  - name: "Sponsor: Lovable"
    type: "sponsor"
    camera_id: "CAM-10"
    floor: 2
    capacity: 20
    sponsor_name: "Lovable"
    polygon: [[50, 50], [300, 50], [300, 250], [50, 250]]
```

**Zone loader:** `backend/utils/zone_loader.py` — reads zones.yaml, returns list of zone configs. Each camera worker filters to zones matching its camera_id.

**Zone types:** coding, mentoring, presenting, networking, sponsor, food, rest. These map directly to activity labels in the activity classifier.

**For Phase 2 testing:** Create a test zones.yaml with at least 3 zones mapped to a test camera. The real venue zones will be configured during Phase 6 (ship-readiness) after visiting the venue.

**Zone polygon drawing tool:** NOT built in this phase. For now, polygon coordinates are manually measured from the camera frame. The visual polygon editor comes in Phase 4 Settings page.

---

## Section 6: Docker Compose Updates

### What to build

Update docker-compose.yml to replace the camera worker placeholder with real camera workers.

**Camera worker services:** One service per camera. All share the same Docker image (backend). Each gets a different `--camera-id` and `--rtsp-url` argument. All get GPU access via nvidia runtime.

For development/testing, define 2-3 camera workers. The rest can be added by duplicating the service definition with different camera IDs.

```yaml
camera-worker-01:
  build: ./backend
  command: python -m workers.camera_worker --camera-id CAM-01 --rtsp-url rtsp://mediamtx:8554/cam01
  depends_on: [redis, mediamtx]
  runtime: nvidia
  volumes:
    - ./models:/app/models:ro
    - ./configs:/app/configs:ro
    - ./data:/app/data
  environment:
    REDIS_URL: redis://redis:6379
    FAISS_INDEX_PATH: /app/data/faiss/faiss_index.bin
    MODELS_DIR: /app/models
    LOG_LEVEL: INFO
  restart: always
  deploy:
    resources:
      reservations:
        devices:
          - capabilities: [gpu]
```

**Shared GPU:** All camera workers share the same physical GPU. ONNX Runtime and CUDA handle GPU memory allocation. Each worker loads its own copy of DEIMv2 into VRAM (~200MB each). With 13 workers: ~2.6GB for DEIMv2 + ~500MB for SCRFD/ArcFace (shared via memory mapping or loaded per-worker) = ~3.1GB of 24GB VRAM. Well within budget.

---

## Section 7: RTMP Testing Setup

### What to build

`scripts/simulate_streams.py` — a script that pushes pre-recorded video files as RTMP streams to MediaMTX for testing. This is how you test the full pipeline without real cameras.

**What the script does:**
1. Takes a video file path and a camera ID as arguments
2. Uses ffmpeg subprocess to push the video as an RTMP stream to `rtmp://localhost:1935/cam{id}`
3. Loops the video indefinitely (so the stream never ends)
4. Supports launching multiple streams simultaneously (one per test camera)

**Usage:**
```bash
# Push a test video as CAM-01
python scripts/simulate_streams.py --video test_video.mp4 --camera-id cam01

# Push multiple cameras
python scripts/simulate_streams.py --video test_video.mp4 --camera-id cam01 &
python scripts/simulate_streams.py --video test_video2.mp4 --camera-id cam02 &
```

**Test videos:** Use any crowd/indoor video from YouTube (download with yt-dlp). Ideal: a video of people working at desks, walking around, standing in groups. Register 2-3 faces from the video manually before testing to verify face matching works.

---

## Section 8: Monitoring Extensions

### What to build

Extend the health check and metrics endpoints from Phase 1 to include camera worker status.

**Camera worker heartbeat:** Each camera worker writes a heartbeat to Redis every 10 seconds:
```
HSET camera_status:{camera_id} last_heartbeat {timestamp}
HSET camera_status:{camera_id} fps {actual_fps}
HSET camera_status:{camera_id} frames_processed {count}
HSET camera_status:{camera_id} faces_detected {count_last_minute}
HSET camera_status:{camera_id} persons_tracked {current_count}
HSET camera_status:{camera_id} status "active"|"reconnecting"|"error"
```

**Health check extension:** GET /api/v1/health now also checks:
- Each camera worker's last heartbeat (stale if >30 seconds ago)
- Reports per-camera status

**Metrics extension:** GET /api/v1/metrics now also reports:
- Per-camera: fps, frames_processed, persons_tracked, faces_detected, status
- Total: events_in_stream (XLEN activity_stream), total_persons_tracked (sum across cameras)

---

## Section 9: Logging for Camera Pipeline

### What to build

Structured log events specific to the camera pipeline. All logged via loguru.

**Per-camera-worker logs:**
- `INFO` on startup: "Camera worker started: camera_id=CAM-01, rtsp_url=rtsp://..., zones_loaded=3"
- `INFO` every 60 seconds: "Pipeline stats: camera_id=CAM-01, fps=9.8, persons=12, identified=10, unidentified=2, zones={Coding A: 8, Mentor: 2}"
- `INFO` on new identification: "Identity linked: track_id=42, participant=Riya Sharma (abc-123), similarity=0.78"
- `WARNING` on low similarity match: "Low confidence match: track_id=42, similarity=0.52, threshold=0.5, participant=Riya Sharma"
- `WARNING` on stream timeout: "RTSP stream timeout: camera_id=CAM-01, retry_count=1"
- `INFO` on reconnection: "RTSP reconnected: camera_id=CAM-01, downtime_seconds=3.2"
- `ERROR` on model inference failure: "DEIMv2 inference failed: camera_id=CAM-01, error=..."
- `ERROR` on persistent stream failure: "RTSP stream failed after 5 retries: camera_id=CAM-01"

---

## Section 10: Tests for Phase 2

### What to build

**Unit tests:**
- `tests/unit/test_person_detector.py` — verify DEIMv2 wrapper loads, returns boxes/scores/keypoints with correct shapes. Use a small test image (not a full video). Verify keypoints shape is (N, 49, 3).
- `tests/unit/test_person_tracker.py` — verify supervision ByteTrack integration: feed 3 frames of synthetic detections, verify track IDs persist across frames.
- `tests/unit/test_identity_linker.py` — verify face-to-body matching: given a face bbox inside a body bbox, the linker correctly pairs them. Given a face bbox outside all body boxes, returns no match.
- `tests/unit/test_activity_classifier.py` — verify zone-based + keypoint logic: coding zone + hands forward → "coding", coding zone + hands in lap → "idle", mentor zone → "mentoring".
- `tests/unit/test_zone_loader.py` — verify zones.yaml parsing, filtering by camera_id.

**Integration tests:**
- `tests/integration/test_camera_pipeline.py` — push a 10-second test video via ffmpeg to MediaMTX, start a camera worker, verify activity events appear in Redis Stream within 15 seconds. Verify events contain participant_id, zone, activity, timestamp.
- `tests/integration/test_identity_pipeline.py` — register a known face via POST /register, push a video containing that face, verify the camera worker emits events with the correct participant_id.

---

## What NOT to Build in This Phase

- No scoring calculation — events flow into Redis Stream but nothing consumes them yet (Phase 3)
- No CCTV wall dashboard — annotated frames are generated but not served to the browser (Phase 3)
- No WebSocket channels — no live data push to frontend (Phase 3)
- No leaderboard — no score ranking (Phase 3)
- No heatmap visualization — zone occupancy data is in Redis but not rendered (Phase 4)
- No alerts — no capacity warnings (Phase 4)
- No sponsor entry/exit counting with LineZone — just PolygonZone for zones (Phase 5)
- No zone polygon editor UI — zones configured via YAML (Phase 4 Settings page)
- No PDF export (Phase 5)

---

## Acceptance Criteria

- [ ] DEIMv2 ONNX model loads successfully and produces bounding boxes + 49 keypoints on a test image
- [ ] supervision ByteTrack assigns persistent track IDs across consecutive frames — same person gets same ID for at least 30 consecutive frames
- [ ] DetectionsSmoother reduces detection flickering (visually confirm on test video)
- [ ] SCRFD + ArcFace correctly identifies a registered participant's face from a video frame (similarity > 0.5)
- [ ] Identity linker correctly maps a face detection to the containing body detection's track ID
- [ ] Once identified, a track maintains its participant_id for the duration of the track (until the person leaves the camera view)
- [ ] sv.PolygonZone correctly reports which tracked persons are inside each defined zone
- [ ] Activity classifier returns correct activities: "coding" for coding zone + hands forward, "mentoring" for mentor zone, "idle" for coding zone + hands in lap
- [ ] Camera worker processes frames from a simulated RTMP stream at ≥8 FPS sustained
- [ ] Activity events appear in Redis Stream (XLEN activity_stream > 0) within 5 seconds of starting the camera worker
- [ ] Each activity event in Redis contains: participant_id, camera_id, zone, activity, timestamp, confidence
- [ ] Zone occupancy in Redis (HGETALL zone_occupancy) updates correctly as people move between zones in test video
- [ ] Camera worker heartbeat appears in Redis (HGETALL camera_status:CAM-01) with fps and status
- [ ] Camera worker reconnects automatically when RTSP stream is interrupted and resumed
- [ ] Running 2 camera workers simultaneously on the GPU VM uses <4GB VRAM total
- [ ] Annotated frames show: color-coded bounding boxes (green/blue/orange/purple/gray), name labels for identified persons, "Unknown" for unidentified
- [ ] Health endpoint reports camera worker status (active, fps, persons tracked)
- [ ] All new unit and integration tests pass
- [ ] simulate_streams.py successfully pushes a looping RTMP stream to MediaMTX

---

## How to Give This to Cursor

```
Read .cursorrules, PROJECT.md, and docs/PHASE_2_SPEC.md. This is Phase 2 of SpatialScore.
Phase 1 is complete — registration, auth, database, Docker Compose are all working.
Create a detailed implementation plan: list every file to create/modify, what each contains,
and the build order. Present the plan and wait for approval before writing code.
```
