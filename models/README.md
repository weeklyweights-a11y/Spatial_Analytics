# Model Weights

Download ONNX models to this directory before running the API with face registration.

| File | Size | Purpose | Phase |
|------|------|---------|-------|
| `scrfd_10g.onnx` | ~16 MB | Face detection (SCRFD-10G) | 1 |
| `arcface_r100.onnx` | ~166 MB | Face embedding (ArcFace-R100) | 1 |
| `deimv2_s_wholebody49.onnx` | ~40 MB | Person detection + 49 keypoints | 2 (download now) |

## Quick setup

```bash
./scripts/download_models.sh
ls -lh models/
```

## Manual download (InsightFace buffalo_l)

```bash
pip install insightface
python -c "from insightface.app import FaceAnalysis; app = FaceAnalysis('buffalo_l', providers=['CPUExecutionProvider']); app.prepare(ctx_id=-1)"
cp ~/.insightface/models/buffalo_l/det_10g.onnx models/scrfd_10g.onnx
cp ~/.insightface/models/buffalo_l/w600k_r50.onnx models/arcface_r100.onnx
```

Or HuggingFace:

```bash
wget https://huggingface.co/public-data/insightface/resolve/main/models/buffalo_l/det_10g.onnx -O models/scrfd_10g.onnx
wget https://huggingface.co/public-data/insightface/resolve/main/models/buffalo_l/w600k_r50.onnx -O models/arcface_r100.onnx
```

## DEIMv2 export (Phase 2 — VM host only, not Docker)

```bash
./scripts/export_deimv2.sh
# Or manually:
# DEIMV2_DIR=/tmp/deimv2 DEIMV2_CHECKPOINT=weights/deimv2_s_wholebody49.pth ./scripts/export_deimv2.sh
```

Verify after export:

```bash
python -c "
import onnxruntime as ort
sess = ort.InferenceSession('models/deimv2_s_wholebody49.onnx', providers=['CPUExecutionProvider'])
print('Outputs:', [o.name for o in sess.get_outputs()])
"
```

**Fallback (document in code, never Ultralytics in Docker):** If wholebody49 export fails, use DEIMv2 det-only + RTMPose ONNX. `PersonDetector` interface stays `(boxes, scores, keypoints)` with shape `(N,49,3)` or `(N,17,3)` fallback.

**PyTorch inference is NOT allowed in Docker** — export scripts run on VM host venv only.

## License

InsightFace buffalo_l pretrained models are **non-commercial research** use. Contact recognition-oss-pack@insightface.ai for commercial licensing. See [RESOURCES.md](../RESOURCES.md).
