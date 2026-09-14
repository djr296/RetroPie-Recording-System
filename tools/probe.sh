#!/bin/bash
set -u

section() { printf '\n===== %s =====\n' "$1"; }

section SYSTEM
cat /etc/os-release 2>/dev/null || true
uname -a
cat /proc/cmdline
id

section DEVICES
ls -la /dev/dri /dev/fb* 2>&1 || true
for device in /dev/dri/card* /dev/fb*; do
    [[ -e "$device" ]] && stat -c '%A %U %G %n' "$device"
done

section FFMPEG
command -v ffmpeg || true
ffmpeg -version 2>&1 | head -n 5 || true
echo '-- capture formats --'
ffmpeg -hide_banner -formats 2>&1 | grep -E 'kmsgrab|fbdev|x11grab|alsa' || true
echo '-- encoders --'
ffmpeg -hide_banner -encoders 2>&1 | grep -E 'h264_(v4l2m2m|omx)|libx264|aac' || true

section ALSA
command -v aplay || true
aplay -l 2>&1 || true
echo '-- named playback PCMs --'
aplay -L 2>&1 || true
echo '-- capture devices --'
arecord -l 2>&1 || true
echo '-- loopback module availability --'
modinfo snd-aloop 2>&1 | head -n 20 || true
lsmod | grep -E '^snd_aloop\b' || true

section RETROARCH
grep -RhsE '^[[:space:]]*(video_driver|audio_driver|audio_device)[[:space:]]*=' \
    /opt/retropie/configs/all/retroarch.cfg \
    /opt/retropie/configs/*/retroarch.cfg 2>/dev/null | sort -u || true

section DISPLAY
tvservice -s 2>&1 || true
fbset -s 2>&1 || true

