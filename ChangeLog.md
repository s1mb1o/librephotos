# Change log

## 2026-11-02 — MCP adapter

Added a separate MCP service with nine read tools, stdio, authenticated Streamable HTTP, per-subject API-key mappings, and optional metadata, album, scan, and caption tools. Added bounded automation REST endpoints. Added a non-root Docker image and deployment documentation.

## 2026-11-02 — Permanent API keys

- Keep standard HTTP header names outside the JSON snake_case guard. Preserve JSON and query parameter checks.
Added named API keys, optional expiration, immediate revocation, read-only defaults, explicit capabilities, authenticated media, account settings, and API contracts. Secrets are shown once and stored only as verifiers. Administrator keys remain owner-scoped for jobs and metadata. API-key headers cannot use JWT cookies to bypass upload restrictions.

## 2026-11-02

- Saved image captioning as enabled on docker-srv. Verified the configured OpenAI API model `qwen3.5-9b-nvfp4` is advertised by the provider.
- Verified that the admin feature is enabled and unlocked. Preserved running processing jobs without a restart.
- Documented the misleading local-service tooltip in remote captioning mode.

- Extended the verified deployment drain to preserve per-photo tag generation after the initial scan.
- Added Test beside remote model settings. Validate draft captioning and image/text embedding requests before saving.
- Reuse saved tokens without exposing them. Keep provider selection, jobs, cached vectors, and indexes unchanged during tests.

- Deployed the remote AI image to docker-srv. Preserved the active scan and all 62 pre-existing catalog and queue tables.
- Added a frozen checkpoint, offline migration verification, and scan advancement checks to the deployment helper.
- Added a queue drain that permits worker recycling. Verified pause and resume in an isolated container.
- Recorded the image digest, private recovery location, HTTP checks, and deployment procedure.

## 2026-11-01

- Added OpenAI-compatible captioning with URL, encrypted access token, and model settings in Admin Area.
- Added remote SigLIP2 NaFlex for text search, similar photos, and generated Things.
- Added separate embedding profiles, cached vectors, persistent similarity indexes, and an explicit index build action.
- Added model-change warnings and a rebuild action for each user. Kept the active index during replacement.
- Paused text semantic search when a changed checkpoint uses the same model handle. Preserved manual metadata and local provider defaults.
- Added provider validation, failure and cancellation tests, API schemas, and setup documentation.

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
