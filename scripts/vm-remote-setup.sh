#!/bin/bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
cd ~

mkdir -p spatialscore
tar -xf spatialscore-deploy.tar -C spatialscore
cd spatialscore

# Docker
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER" || true
fi

# .env
if [[ ! -f .env ]]; then
  DB_PASS="$(openssl rand -hex 16)"
  JWT_SECRET="$(openssl rand -hex 24)"
  cat > .env <<EOF
DB_PASSWORD=${DB_PASS}
JWT_SECRET=${JWT_SECRET}
GCS_BUCKET=spatialscore-data
FAISS_INDEX_PATH=/app/data/faiss/faiss_index.bin
EMBEDDING_MAP_PATH=/app/data/faiss/embedding_map.json
MODELS_DIR=/app/models
LOG_LEVEL=INFO
JWT_EXPIRY_HOURS=24
FACE_SIMILARITY_THRESHOLD=0.5
DUPLICATE_REGISTRATION_THRESHOLD=0.6
CORS_ORIGINS=http://localhost:3000,http://104.199.197.111:3000
SCORING_FLUSH_INTERVAL=60
HEATMAP_SNAPSHOT_INTERVAL=300
MAX_REGISTRATION_STATIONS=10
VITE_API_URL=http://104.199.197.111:8000
EOF
  echo "Created .env"
fi

chmod +x scripts/*.sh
mkdir -p data/faces data/faiss data/venue data/exports data/backups logs models

# Face models (InsightFace)
pip3 install --break-system-packages insightface onnxruntime opencv-python-headless 2>/dev/null || pip3 install insightface onnxruntime opencv-python-headless
python3 -c "
from insightface.app import FaceAnalysis
app = FaceAnalysis('buffalo_l', providers=['CPUExecutionProvider'])
app.prepare(ctx_id=-1)
print('buffalo_l ready')
"
BUFFALO="${HOME}/.insightface/models/buffalo_l"
cp "${BUFFALO}/det_10g.onnx" models/scrfd_10g.onnx
cp "${BUFFALO}/w600k_r50.onnx" models/arcface_r100.onnx
ls -lh models/

# DEIMv2 placeholder for Phase 2 — export on GPU VM when L4 quota available
if [[ ! -f models/deimv2_s_wholebody49.onnx ]]; then
  echo "DEIMv2 export deferred — creating empty marker; re-run export when GPU VM is ready"
  echo "Phase 2 export pending" > models/deimv2_export_pending.txt
fi

docker pull postgres:16-alpine
docker pull redis:7-alpine
docker pull bluenviron/mediamtx:latest

# CPU VM: drop nvidia runtime (restore when upgrading to g2 + L4)
sed -i '/runtime: nvidia/d' docker-compose.yml

sudo docker compose up -d --build

sleep 45
curl -sf http://localhost:8000/api/v1/health | python3 -m json.tool || true

sudo docker compose exec -T api python -m backend.cli create-user --username admin --password "SpatialScore2026!" --role admin || true

echo "=== VM setup complete ==="
echo "Dashboard: http://104.199.197.111:3000"
echo "API health: http://104.199.197.111:8000/api/v1/health"
echo "Admin: admin / SpatialScore2026!"
