#!/bin/bash
set -euo pipefail

DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
OUTPUT=/home/pi/RetroPie/recordings-system/yuv-720p30-test.mkv
GRAB_LOG=/home/pi/yuv-720p30-grab.log
START=$(date +%s)

sudo "$DIR/dispmanx-grab" \
    --width 1280 --height 720 --fps 30 --frames 300 --format yuv420p \
    2>"$GRAB_LOG" | \
ffmpeg -hide_banner -loglevel warning -nostdin -y \
    -thread_queue_size 128 -f rawvideo -pixel_format yuv420p \
    -video_size 1280x720 -framerate 30 -i pipe:0 \
    -thread_queue_size 2048 -f alsa -ac 2 -ar 48000 \
    -i hw:CARD=Loopback,DEV=1,SUBDEV=0 \
    -map 0:v:0 -map 1:a:0 -c:v h264_omx -b:v 6000k \
    -c:a aac -b:a 160k -af 'aresample=async=1:first_pts=0' \
    -shortest "$OUTPUT"

END=$(date +%s)
sudo chown pi:pi "$OUTPUT" "$GRAB_LOG"
echo "ELAPSED=$((END - START)) seconds"
cat "$GRAB_LOG"
ls -lh "$OUTPUT"
