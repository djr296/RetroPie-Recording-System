#!/bin/bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo 'Run with sudo.' >&2
    exit 1
fi

python3 - <<'PY'
from pathlib import Path

path = Path('/opt/retropie/configs/all/retroarch.cfg')
if not path.exists():
    raise SystemExit(f'RetroArch configuration not found: {path}')
begin = '# BEGIN RPREC NOTIFICATIONS'
end = '# END RPREC NOTIFICATIONS'
text = path.read_text(encoding='utf-8', errors='replace')
output = []
skipping = False
for line in text.splitlines(True):
    clean = line.rstrip('\r\n')
    if clean == begin:
        skipping = True
    elif skipping and clean == end:
        skipping = False
    elif not skipping:
        output.append(line)
text = ''.join(output).rstrip() + '\n'
text += f'''\n{begin}
network_cmd_enable = "true"
network_cmd_port = "55355"
{end}
'''
path.write_text(text, encoding='utf-8')
print(f'Enabled local recording notifications in {path}')
PY
