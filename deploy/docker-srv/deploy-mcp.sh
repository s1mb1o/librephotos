#!/usr/bin/env bash
set -euo pipefail
repo=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
remote=${LP_REMOTE:-root@192.168.86.16}
revision=$(git -C "$repo" rev-parse --short=12 HEAD)
if [[ -n $(git -C "$repo" status --porcelain) ]]; then revision="${revision}-dirty"; fi
tag="$(date -u +%Y%m%dT%H%M%SZ)-${revision}"
image="registry.my.3simbio.ru/librephotos/mcp:${tag}"
docker build --platform linux/amd64 --progress=plain \
  -f "$repo/deploy/docker/mcp/Dockerfile" -t "$image" "$repo"
docker push "$image"
scp "$repo/deploy/docker-srv/provision_mcp.py" "$remote:/srv/librephotos/bin/provision_mcp.py"
ssh "$remote" python3 /srv/librephotos/bin/provision_mcp.py
ssh "$remote" 'test -s /srv/librephotos/mcp/credentials/principals.json && test -s /srv/librephotos/mcp/credentials/tokens.json'
scp "$repo/deploy/docker-srv/mcp.compose.yaml" "$remote:/srv/librephotos/mcp/compose.yaml"
ssh "$remote" python3 - "$image" <<'PY'
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path('/srv/librephotos/mcp')
lock = (root / '.deploy.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
image = sys.argv[1]
if not image.startswith('registry.my.3simbio.ru/librephotos/mcp:'):
    raise SystemExit('Unexpected MCP image repository')
env = root / '.env'
previous = env.read_text() if env.exists() else ''
(root / 'environment.before.private').write_text(previous)
os.chmod(root / 'environment.before.private', 0o600)
lines = [line for line in previous.splitlines() if not line.startswith('LP_MCP_IMAGE=')]
replacement = root / '.env.next'
replacement.write_text('\n'.join([*lines, 'LP_MCP_IMAGE=' + image]) + '\n')
replacement.chmod(0o600)
replacement.replace(env)
command = ['docker', 'compose', '--env-file', str(env), '-f', str(root / 'compose.yaml')]
subprocess.run([*command, 'config', '--quiet'], check=True)
subprocess.run([*command, 'pull'], check=True)
subprocess.run([*command, 'up', '-d', '--wait', '--wait-timeout', '120'], check=True)
(root / 'deployment.json').write_text(json.dumps({'image': image, 'revision': image.rsplit('-', 1)[-1]}, indent=2) + '\n')
print('MCP deployment complete. The LibrePhotos application was not restarted.')
PY
