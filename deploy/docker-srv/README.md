# LibrePhotos on docker-srv

The Mac builds AMD64 images from this checkout. The LAN registry stores each
build under a unique tag. Docker-srv runs the image and a dedicated PostgreSQL
container. Its external package downloads are unreliable.

## Update

Run from the Mac:

```bash
./deploy/docker-srv/deploy.sh
```

The command includes current uncommitted source changes. It does not push Git.
It reuses the Docker dependency caches and the frontend build when its sources
have not changed. Keep the Docker build cache between builds.

The deployment command copies only Compose and the activation script. Runtime
credentials stay in `/srv/librephotos/.env`, mode `0600`. They never enter the
image or the Git repository. The admin password is stored in macOS Keychain
under `librephotos-docker-srv-admin`, account `ashmelev`.

## State and resources

- URL: `http://192.168.86.16:19850`.
- Host directory: `/srv/librephotos`.
- State: `/srv/librephotos/data/{postgres,protected_media,cache,logs}`.
- Originals: the configured NAS folder, mounted read-only at `/data/PhotoLibrary`.
- Application data root: `/data`. Admin scan directory: `/data/PhotoLibrary`.
- Containers: `librephotos-app` and `librephotos-db`.
- Initial application limit: 2 CPUs and 6 GiB RAM. One scan worker.
- PostgreSQL limit: 1 CPU and 1 GiB RAM. No published database port.
- Video previews and video face detection are disabled initially.

The database, previews, models, and caches survive image replacement.
The admin is created only when missing. Rebuilds preserve password changes.
Never run `docker compose down -v` or delete the state directories to rebuild.
The original directory structure stays unchanged.
The admin account uses semantic search with Top 100 enabled.
Deployment refuses an unavailable library. Startup also checks its existing
`/data/PhotoLibrary/Years` directory before starting the application.
The activation helper checks `/mnt/librephotos/Years` on the host.

The 2026-11-01 remount changed only the Docker target and catalog paths.
The NAS directory and the Proxmox and CT 100 mounts retain their paths.
The migration preserved photo identities and rewrote signed queued scan tasks.
Keep the database scan directory consistent with the Docker target.

## Validation

```bash
ssh root@192.168.86.16 'cd /srv/librephotos && docker compose ps'
curl --fail http://192.168.86.16:19850/api/healthz/ready
ssh root@192.168.86.16 'docker logs --tail 100 librephotos-app'
```

## Backup and rollback

Before each replacement, the activation script stores a PostgreSQL dump and
the previous environment in `/srv/librephotos/backups`. The environment backup
contains credentials. It is readable only by root. These are local recovery
copies. Independent backup coverage must be configured separately.

`deployment.json` records the active and previous image tags. Keep those tags
in the registry. To revert code, restore the previous `LP_IMAGE` in `.env` and
run `docker compose up -d --wait`. If an update migrated the database, restore
the matching database dump before starting the previous image. Do not assume
that an older application can use a newer schema.

The fork still needs code changes for pairing across directories, configurable
remote caption models, and photo quality scoring.

## Initial model installation

Hugging Face downloads work from docker-srv. The default `buffalo_sc` face
archive comes from a GitHub release that docker-srv cannot reach. Download it
through the Mac, verify the SHA-256 in `api/runtime/ml_models.py`, and install
it at `data/protected_media/data_models/face_recognition/models/buffalo_sc`.
The initial deployment has installed all required models. Rebuilds reuse them.
The database stores the selected models. OCR remains disabled by default.

A scan creates thumbnails, search embeddings, tags, and face data. Caption
generation is a separate Library job. The deployment verifies it on one photo.
After the initial scan, use Generate captions to caption the complete library.
