# Smoke tests

## 2026-11-02 — Persistent MCP HTTP deployment

Connect with a persistent MCP token. Refuse missing tokens and LibrePhotos API keys as MCP tokens. Verify two subjects use different account keys. Remove a verifier and confirm immediate HTTP 401. Confirm search and authenticated still previews on docker-srv.

## MCP integration

Connect an official SDK client over stdio and HTTP. Search and retrieve a preview. Test two OAuth subjects with separate keys. Reject expired tokens, incorrect audiences, invalid identifiers, oversized responses, and foreign objects. Verify write tools are absent by default. Enable writes with restricted scopes and verify immediate job identifiers.

## Permanent API keys

Create a permanent read-only key in Settings. Copy it once. Search and fetch an owned preview. Refuse metadata writes and private photos of another user. Revoke the key and verify the next request fails. Verify JWT sign-in remains available.

## Fork initialization

- Verify that `origin` resolves to the personal GitHub fork.
- Verify that the upstream GitHub push URL is disabled.
- Verify that release `1.5.1` is an ancestor of the development branch.
- Verify that upstream branches, tags, and commit history are available.
- Verify that application files match the reviewed release at initialization.
- Verify that the published branch commit matches the local commit.
- Verify that GitHub Actions are disabled during fork initialization.

## Targets for later changes

These checks are pending. They are not passing claims for the initial fork.

- Concurrent moves to one destination preserve both original payloads.
- An interrupted cross-filesystem copy preserves the source and removes staging data.
- RAW, JPEG, Live Photo, and XMP components stay associated after a move.
- A disconnected NAS does not cause deletion of catalog entries or originals.
- Configured caption providers process a fixture and report actionable errors.
- Caption generation preserves manual captions.
- Caption export survives a fresh catalog import.
- Semantic search preserves relevance order with filters and shared libraries.
- Quality scoring records model provenance and preserves manual ratings.
- Similar-photo review requires an explicit decision before original deletion.

## Docker-srv deployment

- Open the LAN URL and verify that the login page renders.
- Verify health, authenticated API access, and one-photo indexing.
- Verify that originals are mounted read-only in Proxmox, CT 100, and Docker.
- Verify that the required models are present.
- Rebuild with a changed revision and confirm cached dependency and frontend layers.
- Replace the application image. Preserve the database, previews, models, and admin password.
- Verify a PostgreSQL backup with `pg_restore --list`.
- Start the PhotoLibrary scan after the deployment checks.

## Active scan image replacement

Verified on 2026-11-02:

- Drain prefetched tasks while permitting worker recycling.
- Preserve the scan job ID, start time, target, and completed counters.
- Verify completed scan groups plus pending groups equal the target.
- Back up frozen PostgreSQL state. Verify the dump with `pg_restore --list`.
- Apply migrations before workers start. Compare all old API and queue rows.
- Retain the PostgreSQL container, original mount, and persistent media.
- Resume the same scan. Verify forward progress and existing media access.
- Keep local model defaults. Verify new Admin Area provider fields.
- Run the isolated 20-task exercise. Verify pause at 8 and resume to 20.

## PhotoLibrary remount

Verified on 2026-11-01:

- The Docker bind maps `/mnt/librephotos` to `/data/PhotoLibrary` read-only.
- `/data/PhotoLibrary/Years` exists. `/data/Years` does not exist.
- The admin scan directory is `/data/PhotoLibrary`. `PHOTOS` remains `/data`.
- All 61 API table fingerprints match after the permitted path normalization.
- All 26,894 queued task payloads match after path normalization.
- Protected-media manifests and 12 original SHA-256 samples match.
- Existing login, caption, photo details, thumbnail, and original access work.
- Health and authenticated media requests return HTTP 200.
- The original scan resumes. The photo count increases after restart.
- The database container and application image remain the same.

Before another path migration, stop the app and back up PostgreSQL and
`protected_media`. Update both catalog paths and signed queued scan tasks.
Keep user captions and photo identities unchanged. Refresh derived search paths.

## Tag generation during image replacement

- Drain a Generate Tags job after all per-photo tasks enter the durable queue.
- Preserve the job ID, start time, target, completed count, and pending photo tasks.
- Verify queue conservation before replacement and forward progress after restart.
- Keep other started job types blocked until they finish.
- Run both scan and tags in the isolated pause exercise.

## Test draft remote settings

- Select a remote model. Confirm Test appears beside Save model settings.
- Change the URL, token, and model. Confirm Test uses the draft without saving it.
- Leave the token blank. Confirm the test uses the saved token.
- Select Remove the saved access token. Confirm Test omits authentication and preserves the saved token.
- Confirm caption tests use a synthetic image. Confirm embedding tests check image and text vectors.
- Refuse invalid URLs, provider errors, empty captions, and incompatible embedding vectors.
- Show a pending state and an inline result. Hide stale results after a field changes or settings save.
- Confirm non-admins cannot test a provider. Confirm catalog rows and active indexes stay unchanged.

## Remote AI models

- [ ] In Admin Area, select OpenAI API. Confirm URL, Access Token, and Model name appear.
- [ ] Save a provider. Reload the page. Confirm the token stays blank and the saved-token hint appears.
- [ ] Generate a caption. Confirm the existing prompt context reaches the provider and a manual caption stays unchanged.
- [ ] Select SigLIP2 NaFlex. Save settings. Build the index and observe job progress.
- [ ] Confirm text search and similar photos use the active profile and preserve relevance order.
- [ ] Fail a provider request and cancel a build. Confirm the prior index still works and the next run reuses cached batches.
- [ ] Restart the similarity sidecar. Confirm both model namespaces load from disk.
- [ ] Switch to OpenCLIP and rebuild. Confirm local behavior and manual metadata remain intact.
- [ ] Confirm a non-admin cannot read connection settings or change providers.
- [ ] Evaluate search and Thing thresholds on representative photos before using the labels for curation.
- [ ] Change the model, endpoint, revision, and patch budget. Confirm a rebuild notice appears before and after saving.
- [ ] Change settings during a build. Confirm that build uses one captured profile.
- [ ] Change the checkpoint revision behind the same endpoint and model. Confirm text semantic search pauses until promotion and metadata search still works.
- [ ] Sign in as a non-admin. Confirm their Library page reports their own pending rebuild and can start it.
