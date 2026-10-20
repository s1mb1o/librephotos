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

The deployment command copies Compose, the activation script, and the scan checkpoint helper. Runtime
credentials stay in `/srv/librephotos/.env`, mode `0600`. They never enter the
image or the Git repository. The admin password is stored in macOS Keychain
under `librephotos-docker-srv-admin`, account `ashmelev`.

## Preserve an active scan

The activation helper pulls the replacement image before maintenance.
It drains prefetched tasks before it stops the application.
Pending tasks remain in PostgreSQL. The scan keeps its job ID and counters.
The helper supports photo scans, per-photo tag generation, and per-photo caption generation.
It refuses other started jobs.
Wait for an embedding rebuild or another unsupported job before deployment.

The helper leases pending ORM tasks while workers finish prefetched tasks.
The feeder thread and worker replacement continue during this drain.
The helper releases the temporary leases on success or failure.
A direct `SIGTERM` can deadlock this django-q2 version during worker recycling.
Do not replace the container until the drain completes.
The helper checks that completed scan groups plus queued groups equal the target.

After the application stops, the helper saves a private recovery checkpoint.
It applies migrations in a separate container with no queue worker.
It compares all pre-existing API and queue rows before releasing stale leases.
It then starts the new image and verifies forward progress of the same scan.
Read [the deployment validation](../../docs/validation/remote-ai-deployment.md).
The isolated pause exercise is in [tests/README.md](tests/README.md).

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

Before each replacement, the activation script stores a frozen PostgreSQL dump,
the previous environment, Compose, scan counters, and verification receipts in
`/srv/librephotos/backups/deploy-<UTC timestamp>/`. The environment backup
contains credentials. It is readable only by root. These are local recovery
copies. Independent backup coverage must be configured separately.

`deployment.json` records the active and previous image tags. Keep those tags
in the registry. To revert code, restore the previous `LP_IMAGE` in `.env` and
run `docker compose up -d --wait`. If an update migrated the database, restore
the matching database dump before starting the previous image. Do not assume
that an older application can use a newer schema.

The fork still needs code changes for pairing across directories and photo
quality scoring. Remote caption and embedding providers are configured in
Admin Area. See `apps/docs/docs/user-guide/settings/remote-ai.md`.

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

## MCP HTTP service

The optional MCP service uses `http://192.168.86.16:19851/mcp` on the LAN.
It requires a persistent bearer token. OAuth is not required in this deployment.
The client token is referenced by macOS Keychain item `librephotos-mcp-docker-srv`,
account `ashmelev`. Do not place the token in Git or a URL.

Runtime files are under `/srv/librephotos/mcp`.
The `credentials` directory contains `principals.json` and `tokens.json`.
The first file contains the scoped LibrePhotos account key.
The second file contains only SHA-256 MCP token verifiers and their subjects.
The service runs as UID 10001. It reads the credentials directory read-only.
It has no photo mount or direct PostgreSQL access. Write tools are disabled.

After credentials exist, run `./deploy/docker-srv/deploy-mcp.sh` on the Mac.
This command builds and pushes a unique AMD64 image through the LAN registry.
It replaces only the MCP container. It does not restart the application.
Revoke a token by removing its verifier from `tokens.json`.
Replace that file atomically inside the mounted credentials directory.
Restart MCP after changing the account-key mapping.
