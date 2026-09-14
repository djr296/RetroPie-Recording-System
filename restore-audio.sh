#!/bin/bash
set -euo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo 'Run with sudo.' >&2
    exit 1
fi

backup=/home/pi/rprec-audio-backup/asound.conf.before-rprec
if [[ -e "$backup" ]]; then
    cp -a "$backup" /etc/asound.conf
else
    rm -f /etc/asound.conf
fi
rm -f /etc/modules-load.d/rprec-loopback.conf /etc/modprobe.d/rprec-loopback.conf
modprobe -r snd-aloop 2>/dev/null || true
echo 'Previous ALSA configuration restored. Reboot the Pi.'
