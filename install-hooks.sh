#!/bin/bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo 'Run with sudo.' >&2
    exit 1
fi
cat > /etc/sudoers.d/rprec-software <<'EOF'
pi ALL=(root) NOPASSWD: /usr/local/bin/rprec game-start *, /usr/local/bin/rprec game-end
EOF
chmod 0440 /etc/sudoers.d/rprec-software
visudo -cf /etc/sudoers.d/rprec-software >/dev/null
python3 - <<'PY'
from pathlib import Path

hook_dir = Path('/opt/retropie/configs/all')
hook_dir.mkdir(parents=True, exist_ok=True)
begin = '# BEGIN RPREC SOFTWARE RECORDER'
end = '# END RPREC SOFTWARE RECORDER'
blocks = {
    'runcommand-onstart.sh': 'sudo -n /usr/local/bin/rprec game-start "${1:-unknown}" "${2:-unknown}" "${3:-unknown}" >>/dev/shm/rprec-hook.log 2>&1 &\n',
    'runcommand-onend.sh': 'sudo -n /usr/local/bin/rprec game-end >>/dev/shm/rprec-hook.log 2>&1\n',
}
for name, command in blocks.items():
    path = hook_dir / name
    if path.exists():
        text = path.read_text()
    else:
        text = '#!/bin/bash\n'
    if path.exists():
        backup = path.with_name(path.name + '.rprec-software-backup')
        if not backup.exists():
            backup.write_text(text)
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
    text += f'\n{begin}\n{command}{end}\n'
    path.write_text(text)
    path.chmod(0o755)
    print(f'Installed game-context hook: {path}')
PY
