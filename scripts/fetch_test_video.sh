#!/usr/bin/env bash
# Download test video to test_data/ (gitignored) via yt-dlp.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${ROOT}/test_data"
mkdir -p "$OUT_DIR"

URL="${1:-}"
OUT_FILE="${OUT_DIR}/test_video.mp4"

if [[ -z "$URL" ]]; then
  echo "Usage: $0 <youtube-or-video-url> [output_filename]"
  echo "Example: $0 'https://www.youtube.com/watch?v=XXXX'"
  exit 1
fi

if [[ -n "${2:-}" ]]; then
  OUT_FILE="${OUT_DIR}/${2}"
fi

if ! command -v yt-dlp &>/dev/null; then
  pip install yt-dlp
fi

yt-dlp -f 'bestvideo[height<=1080]+bestaudio/best[height<=1080]' \
  --merge-output-format mp4 \
  -o "$OUT_FILE" \
  "$URL"

echo "Saved: $OUT_FILE"
