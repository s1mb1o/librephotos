# Change log

## 2026-11-02 — Recent caption job results

- Added a recent-results card to caption job pages with previews, caption snapshots, outcomes and processing times.
- Retain the latest 20 results per job. Merge concurrent worker updates and preserve progress, errors and cancellation.
- Restrict the feed to the job owner and currently available owned photos. Keep snapshot data out of existing job serializers.
- Poll through the final result response. Preserve recorded results after the job finishes.


## 2026-11-02 — Identity-aware captions deployed

- Deployed image 20261102T070136Z-1680406af0f2 on docker-srv with API keys and MCP preserved.
- Verified all 67 existing catalog and queue tables. Retained 32166 photos and the database container.
- Paused Generate Captions at 764 of 32089 and resumed the same job. Verified forward progress and authenticated MCP access.
- Recorded the private recovery checkpoint and live caption metadata. Real-model named output remains unverified.


## 2026-11-02 — Queue feeder correction

- Replace pusher suspension with temporary pending-task leases during deployment. Keep feeder threads active.
- Restore pending leases on success or failure. Test the production prefetch size and large task messages.

## 2026-11-02 — Identity-aware caption deployment preparation

- Combined identity-aware captions with the deployed API-key and MCP code.
- Extended the verified task-boundary drain to Generate Captions. Preserve its job ID, counters and queued photo tasks.

## 2026-11-02 — Persistent MCP HTTP deployment

Deployed application and MCP images from revision `c7c165ac849c` on docker-srv. Preserved 32,166 photos and all 66 original catalog and queue tables. Verified live API keys, persistent-token revocation, semantic search, similarity, previews, people, jobs, and the API Keys browser interface.

Added persistent MCP HTTP bearer tokens with verifier-only storage, immediate revocation, per-account keys, and a LAN deployment service. Preserved the deployed model-settings Test action.

## 2026-11-02 — MCP adapter

Added a separate MCP service with nine read tools, stdio, authenticated Streamable HTTP, per-subject API-key mappings, and optional metadata, album, scan, and caption tools. Added bounded automation REST endpoints. Added a non-root Docker image and deployment documentation.

## 2026-11-02 — Permanent API keys

- Keep standard HTTP header names outside the JSON snake_case guard. Preserve JSON and query parameter checks.
Added named API keys, optional expiration, immediate revocation, read-only defaults, explicit capabilities, authenticated media, account settings, and API contracts. Secrets are shown once and stored only as verifiers. Administrator keys remain owner-scoped for jobs and metadata. API-key headers cannot use JWT cookies to bypass upload restrictions.

## 2026-11-02

- Created [GitHub issue #8](https://github.com/s1mb1o/librephotos/issues/8) for face-grounded captions. Linked the implementation and validation.

- Added face-grounded generated captions with numbered boxes and stable reference tokens.
- Resolve confirmed labels and strict agreeing predictions to names inside LibrePhotos.
- Update names after relabeling, renaming, rejection, confidence changes, and bulk prediction writes.
- Regenerate changed geometry in the background. Reject stale responses and preserve concurrent manual captions.
- Keep internal face evidence out of photo responses and shared search. Retry stale captions through Generate captions.

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
