#!/usr/bin/env bash
# SpatialScore GCP VM bootstrap — run once on fresh GCE g2-standard-8 (Ubuntu 24.04)
set -euo pipefail

echo "=== SpatialScore GCP Setup ==="
echo "Ensure gcloud is configured: gcloud config set project YOUR_PROJECT_ID"

# 1. NVIDIA driver 550
echo "Install NVIDIA driver 550 (if not present)..."
if ! command -v nvidia-smi &>/dev/null; then
  sudo apt-get update
  sudo apt-get install -y nvidia-driver-550
  echo "Reboot required after driver install, then re-run this script."
  exit 0
fi

# 2. Docker + Compose
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
fi

# 3. NVIDIA Container Toolkit
if ! dpkg -l | grep -q nvidia-container-toolkit; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
  sudo apt-get update
  sudo apt-get install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker
fi

# 4. Clone repo (if not already)
if [[ ! -f docker-compose.yml ]]; then
  echo "Clone the repo into this directory first."
  exit 1
fi

# 5. Environment
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Edit .env — set DB_PASSWORD and JWT_SECRET (32+ chars), then re-run."
  exit 0
fi

# 6. Models
chmod +x scripts/*.sh
./scripts/download_models.sh
./scripts/setup_reference_repos.sh

# 7. Data dirs
mkdir -p data/faces data/faiss data/venue data/exports data/backups logs models

# 8. Pull images
docker pull bluenviron/mediamtx:latest
docker pull postgres:16-alpine
docker pull redis:7-alpine

# 9. Start stack (Alembic runs via api entrypoint)
docker compose up -d --build

# 10. Wait for API
sleep 15
curl -sf http://localhost:8000/api/v1/health | python3 -m json.tool || echo "Health check pending..."

# 11. Create admin user
echo "Create admin user:"
docker compose exec api python -m backend.cli create-user --username admin --password changeme123456 --role admin

echo "=== Setup complete ==="
echo "Dashboard: http://$(curl -s ifconfig.me 2>/dev/null || echo localhost):3000"
echo "See docs/BROWSER_E2E_CHECKLIST.md for manual verification."
