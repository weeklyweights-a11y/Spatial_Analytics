#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git curl wget python3 python3-pip python3-venv
echo "SpatialScore bootstrap complete" > /var/log/spatialscore-bootstrap.log
