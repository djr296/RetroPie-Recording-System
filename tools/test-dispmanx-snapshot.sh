#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

width=${1:-1280}
height=${2:-720}
raw=/home/pi/RetroPie/recordings-system/dispmanx-test.raw
png=/home/pi/RetroPie/recordings-system/dispmanx-test.png

./dispmanx-grab --width "$width" --height "$height" --fps 1 --frames 1 > "$raw"
ffmpeg -hide_banner -loglevel error -y \
    -f rawvideo -pixel_format rgb565le -video_size "${width}x${height}" \
    -i "$raw" -frames:v 1 "$png"
chown pi:pi "$raw" "$png" 2>/dev/null || true
echo "Created $png"
ls -lh "$raw" "$png"
