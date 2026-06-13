#!/usr/bin/env bash
# Export DEIMv2-wholebody49 to ONNX (run on VM host venv — PyTorch NOT in Docker image).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT="${ROOT}/models/deimv2_s_wholebody49.onnx"
DEIMV2_DIR="${DEIMV2_DIR:-/tmp/deimv2}"

echo "=== DEIMv2 ONNX export ==="

if [[ ! -d "$DEIMV2_DIR" ]]; then
  git clone --depth 1 https://github.com/Intellindust-AI-Lab/DEIMv2.git "$DEIMV2_DIR"
fi

cd "$DEIMV2_DIR"

if [[ -f requirements.txt ]]; then
  pip install -r requirements.txt
fi

CONFIG="${DEIMV2_CONFIG:-configs/deimv2_s_wholebody49.yml}"
CHECKPOINT="${DEIMV2_CHECKPOINT:-weights/deimv2_s_wholebody49.pth}"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: config not found: $CONFIG"
  echo "Download checkpoint per DEIMv2 README and set DEIMV2_CONFIG / DEIMV2_CHECKPOINT"
  exit 1
fi

if [[ -f tools/export_onnx.py ]]; then
  python tools/export_onnx.py \
    --config "$CONFIG" \
    --checkpoint "$CHECKPOINT" \
    --output "$OUTPUT"
else
  echo "ERROR: tools/export_onnx.py not found in DEIMv2 repo"
  exit 1
fi

python -c "
import onnxruntime as ort
sess = ort.InferenceSession('${OUTPUT}', providers=['CPUExecutionProvider'])
print('Input:', sess.get_inputs()[0].name, sess.get_inputs()[0].shape)
print('Outputs:', [(o.name, o.shape) for o in sess.get_outputs()])
print('Export OK: ${OUTPUT}')
"
