#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODELS_DIR="${ROOT}/models"
mkdir -p "$MODELS_DIR"

echo "=== SpatialScore model download ==="

# Option B first on headless VMs (no libGL required)
wget -q "https://huggingface.co/public-data/insightface/resolve/main/models/buffalo_l/det_10g.onnx" \
  -O "${MODELS_DIR}/scrfd_10g.onnx" || true
wget -q "https://huggingface.co/public-data/insightface/resolve/main/models/buffalo_l/w600k_r50.onnx" \
  -O "${MODELS_DIR}/arcface_r100.onnx" || true

# Option A: InsightFace buffalo_l (SCRFD + ArcFace) if wget failed
if command -v python3 &>/dev/null; then
  PYTHON=python3
else
  PYTHON=python
fi

if ! $PYTHON -c "import insightface" 2>/dev/null; then
  echo "Installing insightface for model download..."
  pip install insightface
fi

$PYTHON -c "
from insightface.app import FaceAnalysis
app = FaceAnalysis('buffalo_l', providers=['CPUExecutionProvider'])
app.prepare(ctx_id=-1)
print('buffalo_l downloaded')
"

BUFFALO="${HOME}/.insightface/models/buffalo_l"
if [[ -f "${BUFFALO}/det_10g.onnx" ]]; then
  cp "${BUFFALO}/det_10g.onnx" "${MODELS_DIR}/scrfd_10g.onnx"
  cp "${BUFFALO}/w600k_r50.onnx" "${MODELS_DIR}/arcface_r100.onnx"
else
  echo "Option B: wget from HuggingFace..."
  wget -q "https://huggingface.co/public-data/insightface/resolve/main/models/buffalo_l/det_10g.onnx" \
    -O "${MODELS_DIR}/scrfd_10g.onnx"
  wget -q "https://huggingface.co/public-data/insightface/resolve/main/models/buffalo_l/w600k_r50.onnx" \
    -O "${MODELS_DIR}/arcface_r100.onnx"
fi

# DEIMv2 — export on VM (Phase 2); placeholder instructions if not present
DEIMV2_OUT="${MODELS_DIR}/deimv2_s_wholebody49.onnx"
if [[ ! -f "$DEIMV2_OUT" ]]; then
  echo "DEIMv2 not found. Clone and export manually:"
  echo "  git clone https://github.com/Intellindust-AI-Lab/DEIMv2.git /tmp/deimv2"
  echo "  cd /tmp/deimv2 && python tools/export_onnx.py --config configs/deimv2_s_wholebody49.yml --output ${DEIMV2_OUT}"
  echo "If wholebody49 config missing, use closest pose variant and document in models/README.md"
fi

missing=0
for f in scrfd_10g.onnx arcface_r100.onnx deimv2_s_wholebody49.onnx; do
  if [[ ! -f "${MODELS_DIR}/${f}" ]]; then
    echo "ERROR: missing ${MODELS_DIR}/${f}"
    missing=1
  fi
done

if [[ $missing -ne 0 ]]; then
  exit 1
fi

echo "All models present:"
ls -lh "${MODELS_DIR}"/*.onnx
