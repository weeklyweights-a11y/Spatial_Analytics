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
