# Reference Repositories

Study-only clones (via `scripts/setup_reference_repos.sh`). **Do not copy-paste** — rewrite into our async/Pydantic/loguru structure.

## vectornguyen76/face-recognition

| Upstream | Our file | Take |
|----------|----------|------|
| `face_detection/` | `backend/core/face_detector.py` | SCRFD preprocessing, ONNX session, output parsing |
| `face_alignment/` | `backend/core/face_recognizer.py` | 5-point affine → 112×112 |
| `face_recognition/arcface/` | `backend/core/face_recognizer.py` | ArcFace inference, L2 normalize |

## yakhyo/face-reidentification

| Upstream | Our file | Take |
|----------|----------|------|
| FAISS IndexFlatIP | `backend/core/face_matcher.py` | add/search/save/load, L2-normalize before IndexFlatIP |

## zerokhong1/face-recognition-system

| Upstream | Our file | Take |
|----------|----------|------|
| `backend/main.py` | `backend/main.py` | App factory, lifespan, routers, middleware |
| `dashboard/src/` | `dashboard/src/` | pages/, components/, hooks/ layout pattern |

## roboflow/supervision (Phase 2)

| Upstream docs | Our file | Take |
|---------------|----------|------|
| ByteTrack + manual Detections | `backend/core/person_tracker.py` | `sv.ByteTrack`, `DetectionsSmoother`, no `from_ultralytics` |
| PolygonZone tutorial | `backend/core/zone_classifier.py` | `PolygonZone.trigger`, centroid assignment |
| Annotators | `backend/workers/camera_worker.py` | Box, Label, HeatMap, Trace annotators |
| RTSP generator | `backend/utils/stream.py` | `get_video_frames_generator` + reconnect |

## Intellindust-AI-Lab/DEIMv2 (Phase 2)

| Upstream | Our file | Take |
|----------|----------|------|
| ONNX export / inference | `backend/core/person_detector.py` | Preprocess, NMS, 49-keypoint output parsing |
| `scripts/export_deimv2.sh` | VM-only export workflow | |

## dronefreak/human-action-classification (Phase 2)

| Upstream concept | Our file | Take |
|------------------|----------|------|
| Keypoint angles / motion heuristics | `backend/core/activity_classifier.py` | Zone + wrist position rules for coding/collaborating/idle |

## roboflow/supervision — LineZone (Phase 5)

| Upstream docs | Our file | Take |
|---------------|----------|------|
| [LineZone tutorial](https://supervision.roboflow.com/latest/detection/tools/line_zone/) | `backend/core/sponsor_line_tracker.py` | `sv.LineZone.trigger` for sponsor entry/exit |
| Line definitions in YAML | `configs/zones.yaml` (`sponsor_lines`) | Entrance lines separate from booth polygons |

## crowdbotp/OpenTraj (Phase 5)

| Upstream | Our file | Take |
|----------|----------|------|
| ETH/UCY TSV schema | `backend/core/trajectory_export.py` | `frame_id`, `pedestrian_id`, `pos_x`, `pos_y`, `activity`, `zone` |
| Anonymized exports | `backend/api/export.py` | SHA256 participant ids when `anonymize=true` |
