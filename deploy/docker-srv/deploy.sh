#!/usr/bin/env bash
set -euo pipefail
repo=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
remote=${LP_REMOTE:-root@192.168.86.16}
revision=$(git -C "$repo" rev-parse --short=12 HEAD)
if [[ -n $(git -C "$repo" status --porcelain) ]]; then revision="${revision}-dirty"; fi
tag="$(date -u +%Y%m%dT%H%M%SZ)-${revision}"
image="registry.my.3simbio.ru/librephotos/app:${tag}"
docker build --platform linux/amd64 --progress=plain \
  --build-arg "GIT_HASH=$revision" --build-arg "IMAGE_TAG=$tag" \
  -f "$repo/deploy/docker-srv/Dockerfile" -t "$image" "$repo"
docker push "$image"
scp "$repo/deploy/docker-srv/compose.yaml" "$remote:/srv/librephotos/compose.yaml"
scp "$repo/deploy/docker-srv/activate.py" "$remote:/srv/librephotos/bin/activate.py"
scp "$repo/deploy/docker-srv/scan_checkpoint.py" "$remote:/srv/librephotos/bin/scan_checkpoint.py"
ssh "$remote" python3 /srv/librephotos/bin/activate.py "$image"
