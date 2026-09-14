#!/bin/bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo 'Run with sudo.' >&2
    exit 1
fi

backup_dir=/home/pi/rprec-audio-backup
mkdir -p "$backup_dir"
if [[ -e /etc/asound.conf && ! -e "$backup_dir/asound.conf.before-rprec" ]]; then
    cp -a /etc/asound.conf "$backup_dir/asound.conf.before-rprec"
fi
if [[ -e /etc/modules-load.d/rprec-loopback.conf ]]; then
    cp -a /etc/modules-load.d/rprec-loopback.conf "$backup_dir/"
fi
if [[ -e /etc/modprobe.d/rprec-loopback.conf ]]; then
    cp -a /etc/modprobe.d/rprec-loopback.conf "$backup_dir/"
fi

cat > /etc/modules-load.d/rprec-loopback.conf <<'EOF'
snd-aloop
EOF
cat > /etc/modprobe.d/rprec-loopback.conf <<'EOF'
options snd-aloop index=2 id=Loopback pcm_substreams=1
EOF

modprobe -r snd-aloop 2>/dev/null || true
modprobe snd-aloop index=2 id=Loopback pcm_substreams=1

hdmi_pcm=${RPREC_HDMI_PCM:-}
if [[ -z "$hdmi_pcm" ]]; then
    card_number=$(aplay -l | sed -n '/^card .*HDMI/{s/^card \([0-9][0-9]*\):.*/\1/p;q;}')
    device_number=$(aplay -l | sed -n '/^card .*HDMI/{s/^card [0-9][0-9]*:.*device \([0-9][0-9]*\):.*/\1/p;q;}')
    if [[ -z "$card_number" || -z "$device_number" ]]; then
        echo 'Could not find an HDMI ALSA output.' >&2
        echo 'Run aplay -l and set RPREC_HDMI_PCM to the correct hw:CARD=...,DEV=... value.' >&2
        exit 1
    fi
    card_id=$(awk -v number="$card_number" '$1 == number {gsub(/[\[\]]/, "", $2); print $2; exit}' /proc/asound/cards)
    if [[ -z "$card_id" ]]; then
        echo "Could not resolve ALSA card $card_number." >&2
        exit 1
    fi
    hdmi_pcm="hw:CARD=$card_id,DEV=$device_number"
fi

cat > /etc/asound.conf <<EOF
# RetroPie Software Recorder: duplicate stereo output to HDMI and snd-aloop.
pcm.rprec_multi {
    type multi
    slaves.hdmi.pcm "$hdmi_pcm"
    slaves.hdmi.channels 2
    slaves.loop.pcm "hw:CARD=Loopback,DEV=0,SUBDEV=0"
    slaves.loop.channels 2
    bindings.0.slave hdmi
    bindings.0.channel 0
    bindings.1.slave hdmi
    bindings.1.channel 1
    bindings.2.slave loop
    bindings.2.channel 0
    bindings.3.slave loop
    bindings.3.channel 1
}

pcm.rprec_route {
    type route
    slave.pcm "rprec_multi"
    slave.channels 4
    ttable.0.0 1
    ttable.1.1 1
    ttable.0.2 1
    ttable.1.3 1
}

pcm.!default {
    type plug
    slave.pcm "rprec_route"
}
EOF

chown -R pi:pi "$backup_dir"
echo "Audio duplication configured for $hdmi_pcm."
echo 'Reboot to activate it. Restore at any time with: sudo rprec-audio-restore'
