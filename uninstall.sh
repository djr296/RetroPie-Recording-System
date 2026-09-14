#!/bin/bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo 'Run with sudo.' >&2
    exit 1
fi

python3 - <<'PY'
from pathlib import Path

begin = '# BEGIN RPREC SOFTWARE RECORDER'
end = '# END RPREC SOFTWARE RECORDER'
for name in ('runcommand-onstart.sh', 'runcommand-onend.sh'):
    path = Path('/opt/retropie/configs/all') / name
    if not path.exists():
        continue
    output = []
    skipping = False
    for line in path.read_text().splitlines(True):
        clean = line.rstrip('\r\n')
        if clean == begin:
            skipping = True
        elif skipping and clean == end:
            skipping = False
        elif not skipping:
            output.append(line)
    path.write_text(''.join(output))

path = Path('/opt/retropie/configs/all/retroarch.cfg')
begin = '# BEGIN RPREC NOTIFICATIONS'
end = '# END RPREC NOTIFICATIONS'
if path.exists():
    output = []
    skipping = False
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines(True):
        clean = line.rstrip('\r\n')
        if clean == begin:
            skipping = True
        elif skipping and clean == end:
            skipping = False
        elif not skipping:
            output.append(line)
    path.write_text(''.join(output), encoding='utf-8')
PY

systemctl disable --now rprec-controller.service 2>/dev/null || true
rm -f /usr/local/bin/rprec /usr/local/bin/rprec-install-hooks \
    /usr/local/bin/rprec-install-notifications /usr/local/bin/rprec-controller-setup \
    /usr/local/bin/rprec-audio-setup /usr/local/bin/rprec-audio-restore \
    /usr/local/bin/rprec-uninstall \
    /etc/sudoers.d/rprec-software \
    /etc/systemd/system/rprec-controller.service
rm -rf /usr/local/lib/rprec
systemctl daemon-reload
echo 'Recorder commands and automatic hooks removed.'
echo 'Recordings, configuration, and audio routing were retained.'
echo 'To restore the old audio configuration, run sudo rprec-audio-restore before uninstalling.'
