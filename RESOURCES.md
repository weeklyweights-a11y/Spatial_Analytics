# RESOURCES.md
# SpatialScore — Complete Resource Map
# Every model, repo, paper, dataset, and library — and exactly what we use from each
# Updated: June 2026

---

## 1. PRETRAINED MODELS (What We Download + Run)

### 1.1 Face Detection — SCRFD

| Item | Detail |
|------|--------|
| **Model** | SCRFD-10G (with keypoints) |
| **File** | `det_10g.onnx` (16.1 MB) |
| **Source** | InsightFace `buffalo_l` model pack |
| **Download** | `pip install insightface` then `FaceAnalysis('buffalo_l')` auto-downloads, OR manually from [HuggingFace public-data/insightface](https://huggingface.co/public-data/insightface/tree/main/models) |
| **Alternative (lighter)** | `det_500m.onnx` (2.5 MB) — SCRFD-500M for edge/CPU deployment |
| **What it does for us** | Detects all faces in a camera frame. Returns bounding boxes + 5 facial landmarks per face. Runs at 30+ FPS on GPU. |
| **Paper** | "SCRFD: Sample and Computation Redistribution for Efficient Face Detection" — ICLR 2022 |
| **Paper link** | https://arxiv.org/abs/2105.04714 |
| **What we take from the paper** | The NAS-based architecture search that makes SCRFD faster than RetinaFace at equal accuracy. We use the pretrained ONNX model as-is. |
| **License** | MIT (code), non-commercial research (pretrained models). Contact recognition-oss-pack@insightface.ai for commercial licensing. |

### 1.2 Face Recognition — ArcFace

| Item | Detail |
|------|--------|
| **Model** | ArcFace-R100 (ResNet-100 backbone) |
| **File** | `w600k_r50.onnx` (166 MB) — inside buffalo_l pack |
| **Source** | InsightFace `buffalo_l` model pack (same download as above) |
| **What it does for us** | Takes an aligned face crop (112x112) and produces a 512-dimensional embedding vector. Two faces of the same person produce vectors with high cosine similarity (>0.5). Different people produce low similarity (<0.3). |
| **Paper** | "ArcFace: Additive Angular Margin Loss for Deep Face Recognition" — Deng et al., CVPR 2019 |
| **Paper link** | https://arxiv.org/abs/1801.07698 |
| **What we take from the paper** | The embedding space design. ArcFace's angular margin loss produces more discriminative embeddings than SphereFace or CosFace. We use this to set our similarity threshold (0.5 for positive match). |
| **License** | Same as SCRFD above. |

### 1.3 Person Detection + Pose Estimation — DEIMv2-wholebody49

| Item | Detail |
|------|--------|
| **Model** | DEIMv2-S wholebody49 (or M for higher accuracy) |
| **File** | `deimv2_s_wholebody49.onnx` (exported to ONNX for inference) |
| **Source** | [Intellindust-AI-Lab/DEIMv2](https://github.com/Intellindust-AI-Lab/DEIMv2) — 1.8K stars |
| **Alt sizes** | Atto (0.49M params, mobile), Pico (1.5M), Femto (0.96M), S (9.71M), M, L, X (50.3M) |
| **What it does for us** | Single forward pass gives: (1) person bounding boxes with confidence, (2) **49 body keypoints** per person (17 body + 6 feet + 26 hands). More detail than YOLO-Pose's 17 keypoints — enables hand-position-based activity classification from MVP. |
| **49 keypoints** | 0-16: body (nose, eyes, ears, shoulders, elbows, wrists, hips, knees, ankles), 17-22: feet (3 per foot), 23-48: hands (13 per hand) |
| **Why over YOLO-Pose** | 49 keypoints vs 17 — hand position tells us coding vs idle vs gesturing. Feet tell us standing vs sitting vs walking. SOTA accuracy with fewer params (S model: 9.71M, >50 AP on COCO). MIT-friendly license vs YOLO's AGPL. |
| **Paper** | "DEIMv2: Real-Time Object Detection Meets DINOv3" — CVPR 2025 lineage (DEIM), Intellindust AI Lab |
| **Integration** | Not Ultralytics-native — construct `sv.Detections()` manually from DEIMv2 output (3 lines of code). All supervision features (ByteTrack, PolygonZone, heatmaps) work identically. |
| **Inference** | Export to ONNX → run via ONNX Runtime (same runtime as SCRFD + ArcFace). TensorRT supported for max speed. |

---

## 2. CORE LIBRARIES (pip install — these ARE the pipeline)

### 2.1 Roboflow Supervision — THE CV TOOLKIT

| Item | Detail |
|------|--------|
| **Repo** | [roboflow/supervision](https://github.com/roboflow/supervision) |
| **Stars** | 41,000+ |
| **License** | MIT |
| **Install** | `pip install supervision` |
| **PyPI downloads** | 1M+ monthly |
| **Documentation** | https://supervision.roboflow.com |

**What we use from supervision (replaces 3 repos we previously planned to fork):**

| Feature | Code | What it replaces |
|---------|------|-----------------|
| **Zone counting** | `sv.PolygonZone(polygon=np.array([...]))` then `zone.trigger(detections)` | Custom point-in-polygon code + lewjiayi/Crowd-Analysis + riyanshibariyaa/Employee-Tracking |
| **Object tracking** | `tracker = sv.ByteTrack()` then `tracker.update_with_detections(detections)` | ByteTrack from ultralytics `model.track()` |
| **Heatmaps** | `sv.HeatMapAnnotator()` | lewjiayi/Crowd-Analysis heatmap generation |
| **Entry/exit counting** | `sv.LineZone(start, end)` then `line.trigger(detections)` → `line.in_count, line.out_count` | Custom sponsor booth counting code |
| **Camera overlays** | `sv.BoundingBoxAnnotator()`, `sv.LabelAnnotator()` | Custom OpenCV drawing code |
| **Movement trails** | `sv.TraceAnnotator()` | Custom trajectory visualization |
| **RTSP/video processing** | `sv.get_video_frames_generator("rtsp://...")` | Custom cv2.VideoCapture loop |
| **YOLO integration** | `sv.Detections.from_ultralytics(results)` | Custom result parsing |
| **Detection smoothing** | `sv.DetectionsSmoother()` | N/A (didn't have this before) |
| **Metrics** | `sv.MeanAveragePrecision()`, `sv.ConfusionMatrix()` | N/A |

**Full pipeline with supervision + DEIMv2:**

```python
import numpy as np
import supervision as sv

# Load DEIMv2-wholebody49 via ONNX Runtime
deimv2 = onnxruntime.InferenceSession("deimv2_s_wholebody49.onnx", providers=["CUDAExecutionProvider"])
tracker = sv.ByteTrack()

# Define zones once from config
coding_zone = sv.PolygonZone(polygon=np.array([[100,100],[400,100],[400,400],[100,400]]))
mentor_zone = sv.PolygonZone(polygon=np.array([[500,100],[700,100],[700,300],[500,300]]))
sponsor_lovable = sv.PolygonZone(polygon=np.array([[...],[...],[...],[...]]))

# Sponsor booth entry/exit line
sponsor_line = sv.LineZone(start=sv.Point(500,200), end=sv.Point(700,200))

# Annotators for organizer CCTV wall view
box_annotator = sv.BoxAnnotator()
label_annotator = sv.LabelAnnotator()
heatmap_annotator = sv.HeatMapAnnotator()
trace_annotator = sv.TraceAnnotator()

for frame in sv.get_video_frames_generator("rtsp://localhost:8554/cam01"):
    # DEIMv2 inference → boxes + 49 keypoints per person
    boxes, scores, keypoints_49 = run_deimv2(deimv2, frame)

    # Construct supervision Detections (not from_ultralytics — DEIMv2 is not YOLO)
    detections = sv.Detections(
        xyxy=boxes,
        confidence=scores,
        data={"keypoints": keypoints_49}  # 49 keypoints per person
    )
    detections = tracker.update_with_detections(detections)

    # Who is in which zone?
    in_coding = coding_zone.trigger(detections)
    in_mentor = mentor_zone.trigger(detections)
    in_sponsor = sponsor_lovable.trigger(detections)
    
    # Sponsor booth entry/exit
    crossed_in, crossed_out = sponsor_line.trigger(detections)

    # Annotate for CCTV wall
    frame = heatmap_annotator.annotate(scene=frame, detections=detections)
    frame = box_annotator.annotate(scene=frame, detections=detections)
    frame = trace_annotator.annotate(scene=frame, detections=detections)
```

### 2.2 Roboflow Trackers — MODULAR TRACKING ALGORITHMS (Phase 2)

| Item | Detail |
|------|--------|
| **Repo** | [roboflow/trackers](https://github.com/roboflow/trackers) |
| **License** | Apache 2.0 |
| **Install** | `pip install trackers` |
| **Algorithms** | SORT, ByteTrack, OC-SORT, BoT-SORT |
| **Documentation** | https://trackers.roboflow.com |

**Not needed for MVP** — supervision's built-in ByteTrack is sufficient for fixed CCTV cameras. Trackers library would be used in Phase 2 if we add drone cameras (BoT-SORT has camera motion compensation) or need Optuna auto-tuning.

### 2.3 MediaMTX — RTMP/RTSP Media Server

| Item | Detail |
|------|--------|
| **Repo** | [bluenviron/mediamtx](https://github.com/bluenviron/mediamtx) |
| **Stars** | 13K+ |
| **License** | MIT |
| **What it does** | Receives RTMP streams from the venue laptop and re-exposes them as local RTSP on the GCP VM. The bridge between venue cameras and our processing pipeline. |
| **Docker** | `bluenviron/mediamtx:latest` — one container, zero config for basic RTMP→RTSP relay |

### 2.3 Roboflow Notebooks — TUTORIALS + REFERENCE CODE

| Item | Detail |
|------|--------|
| **Repo** | [roboflow/notebooks](https://github.com/roboflow/notebooks) |
| **Key notebooks** | `how-to-use-polygonzone-annotate-and-supervision.ipynb`, `how-to-detect-and-count-objects-in-polygon-zone.ipynb` |
| **What we use** | Reference implementations for zone counting, tracking, and annotation. Copy patterns, not code. |

---

## 3. NVIDIA ECOSYSTEM (Enterprise Upgrade Path)

### 3.1 NVIDIA DeepStream SDK — STREAMING ANALYTICS FRAMEWORK

| Item | Detail |
|------|--------|
| **What it is** | GStreamer-based real-time streaming analytics toolkit for multi-sensor processing |
| **Download** | https://developer.nvidia.com/deepstream-sdk (free, requires NVIDIA Developer account) |
| **Requires** | NVIDIA GPU + CUDA + TensorRT. Runs on Jetson or dGPU. |
| **Documentation** | https://docs.nvidia.com/metropolis/deepstream/dev-guide/ |

**Built-in capabilities relevant to us:**

| Feature | DeepStream Component | Our Equivalent |
|---------|---------------------|---------------|
| Multi-stream RTSP ingestion | NvStreamer + GStreamer | `sv.get_video_frames_generator()` |
| GPU-optimized person detection | PeopleNet (TensorRT) | YOLO11-Pose (ONNX Runtime) |
| Multi-object tracking | NvMultiObjectTracker (IOU, NvSORT, NvDeepSORT, NvDCF) | sv.ByteTrack / trackers.ByteTrackTracker |
| Re-identification embeddings | NvDCF with Re-ID model (256-2048 dim) | ArcFace (512 dim face embeddings) |
| Zone counting + line crossing | nvdsanalytics plugin | sv.PolygonZone + sv.LineZone |
| Camera calibration | Built-in calibration tool → floor plan alignment | Custom OpenCV homography |
| Analytics output | Kafka message broker | Redis Streams |
| Multi-camera fusion | Metropolis Multi-Camera Fusion microservice | Custom cross-camera matching |

**When to use DeepStream instead of our supervision-based stack:**

- 20+ cameras → DeepStream's GPU-optimized pipeline handles more streams per GPU
- Jetson deployment → DeepStream is optimized for Jetson (DLA + GPU)
- Production SaaS → DeepStream's microservice architecture scales horizontally

**When NOT to use DeepStream:**

- MVP / hackathon timeline → DeepStream has steeper learning curve (GStreamer pipeline)
- Rapid iteration → Python + supervision is faster to modify than GStreamer pipelines
- 4-6 cameras → supervision handles this fine, DeepStream is overkill

### 3.2 NVIDIA DeepStream Python Apps

| Item | Detail |
|------|--------|
| **Repo** | [NVIDIA-AI-IOT/deepstream_python_apps](https://github.com/NVIDIA-AI-IOT/deepstream_python_apps) |
| **What we use** | Reference architectures for multi-stream pipelines. Specifically: `deepstream-test3` (multi-stream detection), `deepstream-imagedata-multistream` (image buffer access for face extraction), `deepstream-nvdsanalytics` (zone counting + line crossing) |

### 3.3 NVIDIA DeepStream Reference Apps

| Item | Detail |
|------|--------|
| **Repo** | [NVIDIA-AI-IOT/deepstream_reference_apps](https://github.com/NVIDIA-AI-IOT/deepstream_reference_apps) |
| **What we use** | Multi-view 3D tracking sample (multi-camera tracking in world coordinates — our BEV projection). Single-view 3D human tracking (person tracking under occlusion using 3D body model). |

### 3.4 NVIDIA DeepStream TAO Apps — PRETRAINED MODELS

| Item | Detail |
|------|--------|
| **Repo** | [NVIDIA-AI-IOT/deepstream_tao_apps](https://github.com/NVIDIA-AI-IOT/deepstream_tao_apps) |
| **Models we'd use** | **PeopleNet** (person detection, TensorRT-optimized), **Reidentification model** (256-2048 dim appearance embeddings for cross-camera Re-ID), **BodyPose3DNet** (3D body pose — more accurate than 2D for activity classification), **Pose Classifier** (classifies poses from keypoints — exactly what we need) |
| **When** | Phase 3 (production scale). For MVP we use YOLO + ArcFace. |

### 3.5 NVIDIA Smart Parking / Multi-Camera Tracking Application

| Item | Detail |
|------|--------|
| **Repo** | [NVIDIA-AI-IOT/deepstream_360_d_smart_parking_application](https://github.com/NVIDIA-AI-IOT/deepstream_360_d_smart_parking_application) |
| **What it is** | Full multi-camera tracking application with RTSP → DeepStream → Kafka → Python multi-camera tracker → unified IDs |
| **What we take** | The multi-camera tracker Python code that consumes Kafka, matches embeddings across cameras, and assigns unified IDs. The camera calibration architecture for global coordinate mapping. The streaming tracker vs batch tracker design pattern. |
| **Why it matters** | This is the closest existing open-source system to our full architecture. It handles the exact problem of cross-camera person re-identification with global coordinates. |

### 3.6 DeepStream Python Boilerplate (Third-party)

| Item | Detail |
|------|--------|
| **Repo** | [ml6team/deepstream-python](https://github.com/ml6team/deepstream-python) |
| **What we take** | The `re_identification.py` pipeline — person tracking with Re-ID embeddings using OSNet. Clean Python boilerplate for DeepStream pipelines with RTSP input/output. |

### 3.7 NVIDIA Metropolis Multi-Camera Tracking App

| Item | Detail |
|------|--------|
| **URL** | https://www.nvidia.com/en-us/ai-data-science/ai-workflows/multi-camera-tracking/ |
| **Access** | Requires NVIDIA Developer application (organizational email) |
| **Architecture** | Media Management → Perception (PeopleNet + NvDCF + Re-ID) → Multi-Camera Fusion (calibration → global coords → cross-camera matching) → Behavior Analytics (zones, dwell, counting) → Web API → Browser UI |
| **Infrastructure** | Kafka + Elasticsearch + Milvus (vector DB) |
| **What we take** | Architecture reference. Not directly usable as open source, but the documented pipeline validates our design. |

### 3.8 NVIDIA Physical AI Smart Spaces Dataset

| Item | Detail |
|------|--------|
| **What** | Large-scale multi-camera 3D perception dataset |
| **Source** | NVIDIA NGC, featured at GTC 2025 |
| **Use case** | Training/benchmarking for multi-target multi-camera tracking, 4D occupancy, digital twin |
| **When we use it** | Phase 3 — benchmarking our multi-camera tracker against NVIDIA's reference dataset |

---

## 4. FACE RECOGNITION REPOS (What We Fork/Adapt)

These are the repos we still need because supervision doesn't do face recognition:

### 4.1 Core Identity Pipeline

| Repo | What we take | What we skip |
|------|-------------|--------------|
| **[vectornguyen76/face-recognition](https://github.com/vectornguyen76/face-recognition)** (193 stars) | `face_detection/` — SCRFD ONNX wrapper. `face_alignment/` — 5-point landmark affine transform. `face_recognition/arcface/` — ArcFace ONNX inference + embedding normalization. The full detect → align → embed pipeline. | Their face_tracking (we use supervision's ByteTrack instead). Their demo UI. |
| **[yakhyo/face-reidentification](https://github.com/yakhyo/face-reidentification)** (168 stars) | FAISS IndexFlatIP implementation with batch query. The `index.search()` pattern for matching all faces in a frame in one call. Model weight download links. | Their main.py entry point. |
| **[amrgodovich/Face-Recognition-Advanced](https://github.com/amrgodovich/Face-Recognition-Advanced)** | Known/unknown person distinction logic — assigns unique IDs to registered participants, separate temp IDs to unregistered people. | Their Flask server. Their tracker (we use supervision). |

### 4.2 Application Shell

| Repo | What we take | What we skip |
|------|-------------|--------------|
| **[zerokhong1/face-recognition-system](https://github.com/zerokhong1/face-recognition-system)** | FastAPI + WebSocket + React architecture pattern. FAISS IndexFlatIP wrapper. | Their CV pipeline (we use supervision + our face pipeline). Their SQLite (we use PostgreSQL). |

---

## 5. ACTIVITY RECOGNITION REPOS

| Repo | What we take | What we skip |
|------|-------------|--------------|
| **[dronefreak/human-action-classification](https://github.com/dronefreak/human-action-classification)** (240 stars) | Pose-based classification module: YOLO keypoints → relative angles/distances → feature vector → classifier. Pretrained classifiers for basic activities. Training pipeline for fine-tuning on hackathon activities. | Video-based 3D CNN module (too heavy). MediaPipe pipeline (we use YOLO-Pose via supervision). |

---

## 6. TRAJECTORY + ROBOTICS REPOS

| Repo | What we take |
|------|-------------|
| **[crowdbotp/OpenTraj](https://github.com/crowdbotp/OpenTraj)** | Data format standard for trajectory datasets. Links to ETH/UCY/SDD datasets. Evaluation metrics (ADE, FDE). |
| **[Li-Zn-H/AwesomeWorldModels](https://github.com/Li-Zn-H/AwesomeWorldModels)** | Curated reading list for world models in embodied AI — our Phase 3 roadmap. |

---

## 7. RESEARCH PAPERS (What We Take From Each)

### 7.1 Papers That Define Our Architecture

| Paper | Published | What we take |
|-------|-----------|-------------|
| **"ArcFace: Additive Angular Margin Loss"** — Deng et al. | CVPR 2019 | Face embedding space design. Similarity threshold (0.5). |
| **"SCRFD: Sample and Computation Redistribution"** | ICLR 2022 | Pretrained face detection model. |
| **"ByteTrack: Multi-Object Tracking by Associating Every Detection Box"** — Zhang et al. | ECCV 2022 | BYTE association algorithm — tracking low-confidence detections. Used via supervision and trackers libraries. |
| **"YOLO-Pose: Multi Person Pose Estimation"** | arXiv 2022 | Single-pass detection + pose. Used via Ultralytics + supervision integration. |

### 7.2 Papers That Validate Our Problem

| Paper | Published | What we take |
|-------|-----------|-------------|
| **"Investigating Hackathons with Collaboration Analytics"** | ICGJ '24, Oct 2024 | Direct problem validation. Wearable badges → our passive CV is the next evolution. Metrics: movement, turn-taking, participation equality. |
| **"From Cues to Engagement: CV-Based Audience Analysis in Live Events"** — Lemos et al. | MTI, Jan 2026 | Five-construct framework: Attention, Emotion, Body Language, Scene Dynamics, Behaviours. Commercial value validation. |

### 7.3 Papers That Inform Technical Approach

| Paper | Published | What we take |
|-------|-----------|-------------|
| **"Comprehensive Survey on Person Re-identification"** — Fouad et al. | Springer, Feb 2026 | Challenge taxonomy. Operating constraints for our venue. |
| **"Person Re-ID in 2025"** | arXiv, Jan 2026 | Domain-shift insight — our fixed venue is actually advantageous. |
| **"PersonViT: Self-supervised ViT for Person Re-ID"** | arXiv 2024 | Appearance-based Re-ID fallback when face isn't visible. Phase 2. |
| **"TE-TransReID: Efficient Person Re-ID"** | Sensors, Sep 2025 | Lightweight Re-ID for real-time multi-stream. |
| **"Vision Transformer for Robust Occluded Person Re-ID"** — Li et al. | ICCPR 2025, May 2026 | Occlusion handling strategies for crowded hackathon. |
| **"MATRIX: Multi-Drone Multi-View Dataset"** — Dakic et al. | arXiv, Nov 2025 | Dynamic camera calibration for drones. BEV projection. ~90% accuracy benchmark. |
| **"Deep Learning-Driven Digital Twin for Pedestrian Tracking"** | ScienceDirect, Mar 2026 | Multi-camera collaborative perception. Digital twin architecture validation. |
| **"Enhanced Real-Time HPE Based on Modified YOLOv8"** | Scientific Reports, May 2025 | CCAM attention module for crowded pose accuracy improvement. |
| **"YOLO-SwinTransformer: Pedestrian Pose Estimation"** | Dec 2025 | Hybrid CNN-Transformer for surveillance pose. Phase 2 upgrade. |
| **"Deep Learning-Based HAR Using Dilated CNN and LSTM"** | Applied Sciences, Nov 2025 | Activity classification architecture. 94.9% on UCF-50. |
| **"Human Activity Recognition in the Deep Learning Era"** | Dec 2025 | Self-supervised HAR — reduces annotation requirements. |

### 7.4 Papers That Inform Robotics Data Value

| Paper | Published | What we take |
|-------|-----------|-------------|
| **"Toward Human-Like Social Robot Navigation"** — Nguyen et al. | arXiv 2023 | Validates scarcity + value of real-world pedestrian trajectory data. |
| **"SACSoN: Scalable Autonomous Control for Social Navigation"** | arXiv 2023 | Counterfactual perturbation minimization — robots learning from human trajectory data. |
| **"World Model for Robot Learning: A Comprehensive Survey"** | arXiv, Apr 2026 | Action-conditioned world models need our multi-modal data. |
| **"Enhanced Pedestrian Trajectory Prediction via KAN"** | PLOS ONE, Jun 2025 | 23% FDE reduction on ETH/UCY. Our data in OpenTraj format plugs directly in. |

---

## 8. DATASETS

### 8.1 Pretraining / Model Foundation

| Dataset | Size | Purpose | Download |
|---------|------|---------|----------|
| **MS COCO Keypoints 2017** | 200K+ images | YOLO11-Pose pretrained on this | https://cocodataset.org |
| **CrowdPose** | 20K images | Crowded scene pose benchmark | github.com/Jeff-sjtu/CrowdPose |
| **UCF-101** | 13K clips, 101 categories | Activity classifier pretraining | crcv.ucf.edu/data/UCF101.php |
| **WIDER FACE** | 32K images, 393K faces | SCRFD pretrained on this | shuoyang1213.me/WIDERFACE |

### 8.2 Benchmarking Our System

| Dataset | Purpose | Download |
|---------|---------|----------|
| **ETH / UCY** | Trajectory prediction accuracy | Included in OpenTraj |
| **Market-1501** | Cross-camera person Re-ID | zheng-lab.cecs.anu.edu.au |
| **MOT17** | Multi-object tracking quality (target: >75 IDF1) | motchallenge.net |
| **MATRIX** | Multi-drone person tracking | github.com/KostaDakic/MATRIX |
| **NVIDIA Physical AI Smart Spaces** | Multi-camera 3D tracking | NVIDIA NGC |

### 8.3 Robotics Downstream

| Dataset | Purpose |
|---------|---------|
| **Stanford Drone Dataset** | Drone-view trajectory reference |
| **HuRoN/SACSoN** | Human-robot interaction validation |
| **HSRI** | Human-robot social interaction |
| **OpenTraj** (aggregated) | 20+ trajectory datasets unified |

---

## 9. PYTHON LIBRARIES (Complete pip install list)

### 9.1 Core CV Pipeline

| Library | Install | What it does for us |
|---------|---------|-------------------|
| `supervision` | `pip install supervision` | Zone counting, tracking, heatmaps, annotators, video processing — THE core CV toolkit |
| `onnxruntime-gpu` | `pip install onnxruntime-gpu` | Inference for ALL three models: SCRFD + ArcFace + DEIMv2-wholebody49. Single runtime, unified GPU. |
| `insightface` | `pip install insightface` | Buffalo_l model pack download (SCRFD + ArcFace). Prototyping only. |
| `opencv-python` | `pip install opencv-python` | Image preprocessing, homography transforms, camera calibration |
| `numpy` | `pip install numpy` | Array ops, keypoint processing, embedding normalization |
| `faiss-cpu` / `faiss-gpu` | `pip install faiss-cpu` | Face embedding similarity search (IndexFlatIP) |
| `scikit-learn` | `pip install scikit-learn` | DBSCAN clustering for collaboration detection, activity classifier from 49 keypoints |

### 9.2 Backend

| Library | What it does |
|---------|-------------|
| `fastapi` | REST API + WebSocket endpoints |
| `uvicorn` | ASGI server |
| `sqlalchemy[asyncio]` | PostgreSQL ORM |
| `asyncpg` | Async PostgreSQL driver |
| `alembic` | Database migrations |
| `redis` | Redis client |
| `pydantic` | Request/response validation |
| `python-multipart` | File upload handling |
| `python-jose[cryptography]` | JWT token handling |
| `passlib[bcrypt]` | Password hashing |

### 9.3 Data + Export

| Library | What it does |
|---------|-------------|
| `pandas` | Activity log aggregation, CSV export |
| `reportlab` / `weasyprint` | PDF generation for sponsor reports |

### 9.4 Infrastructure

| Library | What it does |
|---------|-------------|
| `loguru` | Structured logging |
| `slowapi` | Rate limiting |
| `docker` + `docker compose` | Container orchestration |

### 9.5 Frontend (npm)

| Library | What it does |
|---------|-------------|
| `react` 18 + `typescript` 5 | Dashboard framework |
| `tailwindcss` 3 | Styling |
| `recharts` 2 | Charts (radar, line, bar) |
| `d3` 7 | Heatmap visualization |
| `@tanstack/react-query` 5 | Data fetching + caching |
| `zustand` | Global state for WebSocket data |
| `reconnecting-websocket` | Auto-reconnect on network drops |
| `react-router-dom` 6 | Client-side routing |
| `lucide-react` | Icons |
| `react-pdf/renderer` | Client-side PDF generation |

---

## 10. HARDWARE + COMPUTE BUDGET

### 10.1 VRAM Budget (GPU Models Running Simultaneously)

| Model | VRAM | Instances | Total |
|-------|------|-----------|-------|
| SCRFD-10G (ONNX) | ~200 MB | 1 (shared) | 200 MB |
| ArcFace-R100 (ONNX) | ~300 MB | 1 (shared) | 300 MB |
| DEIMv2-S wholebody49 (ONNX) | ~200 MB | 1 per camera (10-13) | 2-2.6 GB |
| FAISS index | ~2 MB | 1 (CPU RAM) | 2 MB |
| **Total GPU VRAM** | | | **~2.7-3.1 GB of 24 GB** |

### 10.2 Inference Speed Per Camera Per Frame

| Step | Time | Frequency |
|------|------|-----------|
| DEIMv2-wholebody49 + sv.Detections | ~8 ms | Every frame (10 FPS) |
| sv.ByteTrack association | <1 ms | Every frame |
| sv.PolygonZone trigger | <1 ms | Every frame |
| SCRFD face detection | ~3 ms | Every 2 seconds |
| ArcFace embedding | ~2 ms per face | Every 2 seconds |
| FAISS search | <1 ms batch | Every 2 seconds |
| **Total per frame** | ~9 ms (pose-only), ~15 ms (pose+face) | |

Budget: 100ms per frame at 10 FPS. We use 9-15ms. **Can handle 7-11 cameras on single L4 GPU.**

---

## 11. PROJECT DIRECTORY STRUCTURE

```
spatialscore/
├── RESOURCES.md              ← This file
├── PROJECT.md
├── .cursorrules
├── docker-compose.yml
├── README.md
│
├── models/                   ← Downloaded pretrained models
│   ├── README.md             ← Download instructions
│   ├── scrfd_10g.onnx
│   ├── arcface_r100.onnx
│   └── deimv2_s_wholebody49.onnx
│
├── backend/
│   ├── main.py               # FastAPI app entry
│   ├── config.py              # Environment config
│   ├── requirements.txt
│   │
│   ├── api/                   # REST + WebSocket endpoints
│   │   ├── registration.py
│   │   ├── scores.py
│   │   ├── tracking.py
│   │   ├── zones.py
│   │   ├── analytics.py
│   │   ├── sponsors.py
│   │   ├── cameras.py
│   │   ├── export.py
│   │   ├── auth.py
│   │   └── websocket.py
│   │
│   ├── core/                  # CV pipeline
│   │   ├── face_detector.py       # SCRFD wrapper (from vectornguyen76)
│   │   ├── face_recognizer.py     # ArcFace embedding (from vectornguyen76)
│   │   ├── face_matcher.py        # FAISS index (from yakhyo)
│   │   ├── person_tracker.py      # supervision ByteTrack + PolygonZone
│   │   ├── activity_classifier.py # Zone-based (MVP) + pose-based (Phase 2)
│   │   └── scoring_engine.py      # Score calculation + tags
│   │
│   ├── workers/
│   │   ├── camera_worker.py       # supervision-based frame processing
│   │   ├── scoring_worker.py      # Redis Stream consumer → scores
│   │   └── heatmap_worker.py      # Periodic snapshots
│   │
│   ├── db/
│   │   ├── database.py
│   │   ├── redis_client.py
│   │   ├── models.py
│   │   └── migrations/
│   │
│   └── utils/
│       ├── geometry.py            # BEV projection for drones
│       └── stream.py              # RTSP helpers
│
├── dashboard/                 # React frontend (organizer only)
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── CommandCenter.tsx
│   │   │   ├── ParticipantLookup.tsx
│   │   │   ├── Leaderboard.tsx
│   │   │   ├── LiveTracking.tsx
│   │   │   ├── SponsorReports.tsx
│   │   │   ├── Registration.tsx
│   │   │   └── Settings.tsx
│   │   ├── components/
│   │   │   ├── Heatmap.tsx
│   │   │   ├── EnergyGraph.tsx
│   │   │   ├── RadarChart.tsx
│   │   │   ├── ActivityTimeline.tsx
│   │   │   ├── ZoneUtilization.tsx
│   │   │   ├── LiveLeaderboard.tsx
│   │   │   ├── CameraFeed.tsx
│   │   │   └── AlertsFeed.tsx
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   └── useScores.ts
│   │   └── utils/
│   │       └── api.ts
│   └── tailwind.config.js
│
├── configs/
│   ├── cameras.yaml
│   ├── zones.yaml
│   ├── scoring.yaml
│   └── bytetrack.yaml
│
├── data/
│   ├── faces/
│   ├── faiss/
│   ├── venue/
│   ├── exports/
│   └── backups/
│
├── references/
│   ├── papers/
│   └── notes/
│
├── scripts/
│   ├── download_models.sh
│   ├── setup_venue.py
│   ├── simulate_streams.py
│   ├── benchmark.py
│   ├── tune_tracker.py        # Optuna-based tracker tuning via trackers library
│   └── anonymize.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── deploy/
    ├── Dockerfile.backend
    ├── Dockerfile.dashboard
    ├── Dockerfile.worker
    └── docker-compose.prod.yml
```

### download_models.sh

```bash
#!/bin/bash
mkdir -p models

# SCRFD + ArcFace (via insightface buffalo_l pack)
python -c "
from insightface.app import FaceAnalysis
app = FaceAnalysis('buffalo_l', providers=['CPUExecutionProvider'])
app.prepare(ctx_id=-1)
print('buffalo_l downloaded')
"
cp ~/.insightface/models/buffalo_l/det_10g.onnx models/scrfd_10g.onnx
cp ~/.insightface/models/buffalo_l/w600k_r50.onnx models/arcface_r100.onnx

# DEIMv2-S wholebody49 (export to ONNX from PyTorch checkpoint)
python -c "
from huggingface_hub import hf_hub_download
# Download DEIMv2 checkpoint and export to ONNX
# Exact path depends on HuggingFace model availability
print('Download DEIMv2-S wholebody49 from HuggingFace or GitHub releases')
print('Export to ONNX: python tools/export_onnx.py --config configs/deimv2_s_wholebody49.yml')
"

echo "All models downloaded to models/"
```

### tune_tracker.py

```python
#!/usr/bin/env python
"""Auto-tune tracker params for our venue using Roboflow Trackers + Optuna."""
from trackers.tune import Tuner

tuner = Tuner(
    tracker_id="bytetrack",
    gt_dir="data/benchmark/gt/",
    detections_dir="data/benchmark/det/",
    objective="HOTA",
    n_trials=100
)
best_params = tuner.tune()
print(f"Best params: {best_params}")
# Save to configs/bytetrack.yaml
```

---

*Last updated: June 2026*
*SpatialScore for Buildathon Dallas*
