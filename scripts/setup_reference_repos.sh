#!/usr/bin/env bash
set -euo pipefail

echo "=== Cloning reference repos to /tmp (study only — not committed) ==="

clone_if_missing() {
  local url="$1"
  local dir="$2"
  if [[ -d "$dir" ]]; then
    echo "Already exists: $dir"
  else
    git clone --depth 1 "$url" "$dir"
  fi
}

clone_if_missing "https://github.com/vectornguyen76/face-recognition.git" /tmp/face-recognition
clone_if_missing "https://github.com/yakhyo/face-reidentification.git" /tmp/face-reid
clone_if_missing "https://github.com/zerokhong1/face-recognition-system.git" /tmp/face-system

cat <<'EOF'

Read these files before implementing:

vectornguyen76/face-recognition:
  /tmp/face-recognition/face_detection/     -> backend/core/face_detector.py
  /tmp/face-recognition/face_alignment/     -> backend/core/face_recognizer.py
  /tmp/face-recognition/face_recognition/arcface/ -> backend/core/face_recognizer.py

yakhyo/face-reidentification:
  FAISS IndexFlatIP patterns                  -> backend/core/face_matcher.py

zerokhong1/face-recognition-system:
  /tmp/face-system/backend/main.py            -> backend/main.py patterns
  /tmp/face-system/dashboard/src/             -> dashboard folder structure

Rule: study, rewrite — no copy-paste.
See docs/REFERENCE_REPOS.md for full mapping.
EOF
