#!/bin/bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo 'Run with sudo.' >&2
    exit 1
fi
DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
missing=false
for command in gcc ffmpeg arecord python3; do
    command -v "$command" >/dev/null || missing=true
done
if [[ "$missing" == true || ! -e /opt/vc/include/bcm_host.h ]]; then
    echo 'Installing required recording packages...'
    apt-get update
    apt-get install -y build-essential ffmpeg alsa-utils libraspberrypi-dev
fi
if [[ ! -x "$DIR/dispmanx-grab" || "$DIR/dispmanx-grab.c" -nt "$DIR/dispmanx-grab" ]]; then
    echo 'Building the Raspberry Pi display capture program...'
    bash "$DIR/build-dispmanx.sh"
fi
install -m 0755 "$DIR/rprec.py" /usr/local/bin/rprec
install -m 0755 "$DIR/install-hooks.sh" /usr/local/bin/rprec-install-hooks
install -m 0755 "$DIR/install-notifications.sh" /usr/local/bin/rprec-install-notifications
install -m 0755 "$DIR/rprec-controller-setup" /usr/local/bin/rprec-controller-setup
install -m 0755 "$DIR/setup-audio.sh" /usr/local/bin/rprec-audio-setup
install -m 0755 "$DIR/restore-audio.sh" /usr/local/bin/rprec-audio-restore
install -m 0755 "$DIR/uninstall.sh" /usr/local/bin/rprec-uninstall
install -d /usr/local/lib/rprec
install -m 0755 "$DIR/dispmanx-grab" /usr/local/lib/rprec/dispmanx-grab
install -m 0755 "$DIR/rprec-session.py" /usr/local/lib/rprec/rprec-session.py
install -m 0755 "$DIR/rprec-controller.py" /usr/local/lib/rprec/rprec-controller.py
if [[ ! -e /etc/rprec-software.json ]]; then
    install -m 0644 "$DIR/config.example.json" /etc/rprec-software.json
fi
install -d -o pi -g pi /home/pi/RetroPie/recordings-system
install -m 0644 "$DIR/rprec-controller.service" /etc/systemd/system/rprec-controller.service
bash "$DIR/install-hooks.sh"
bash "$DIR/install-notifications.sh"
systemctl daemon-reload
systemctl enable --now rprec-controller.service
echo
echo 'RetroPie Software Recorder installed.'
echo 'Next: sudo rprec-audio-setup'
echo 'Then reboot and run: sudo rprec-controller-setup'
