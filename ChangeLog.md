# Change log

## 2026-11-01

- Remounted PhotoLibrary read-only at `/data/PhotoLibrary` on docker-srv.
- Migrated catalog paths and signed scan tasks without changing photo identities.
- Preserved 7,256 photos and their metadata. Verified login, captions, previews,
  original bytes, and continuation of the existing scan.
- Updated the Compose mount and startup guard for subsequent deployments.

- Added the docker-srv deployment at LAN port 19850.
- Added a cached AMD64 build, immutable LAN image tags, and a deployment command.
- Kept PostgreSQL, previews, models, logs, and caches outside the image.
- Added a database backup before replacement and preserved existing admin passwords.
- Mounted only PhotoLibrary read-only inside the application.

- Created a native GitHub fork from the official LibrePhotos repository.
- Removed the GitHub publishing prohibition at the owner's request.
- Based `codex/nas-photo-library` on upstream release `1.5.1`.
- Added fork identity, Git publishing rules, research findings, and smoke targets.
- Preserved upstream application code, license, branches, tags, and history.
- Disabled initial GitHub Actions runs.

Upstream release notes remain under `apps/docs/blog/`.
