# Research log

## 2026-11-02 — Captioning feature and local service status

The owner requested image captioning enablement after a Disabled service tooltip.
The container already had `FEATURE_IMAGE_CAPTIONING=true`.
The saved `IMAGE_CAPTIONING_ENABLED` setting was also true.
The caption provider was `openai_api` with `qwen3.5-9b-nvfp4`.
The enable setting was saved explicitly. The admin API reports enabled and unlocked.
`captioning_available()` returns true. The provider model list returns HTTP 200
and includes the configured model. No generation or processing restart was required.

The Services table reports local sidecar state.
`local_captioning_selected()` disables the local sidecar in remote API mode.
The current frontend wrongly infers an environment lock from any disabled service
that has a `feature_flag`. The screenshot's environment-variable tooltip is incorrect.
Do not switch back to a local model or restart processing to resolve this display.
The enabled remote caption provider does not need the local port 8007 service.

## 2026-11-02 — Test draft model settings

A model-list request does not verify image input or the embedding dimension.
The Test action therefore uses the existing inference clients with synthetic input.
Captioning checks nonempty final text. SigLIP2 checks both image and text vectors.
Draft settings merge with saved credentials in memory. The test does not save them.
The response contains only the provider kind and nullable vector dimension.
Provider response bodies and credentials stay out of error messages.
A result applies only while the form matches the tested values.

The photo scan finished while this update was in validation.
Its automatic Generate Tags job queues one task per photo.
`generate_tag_job` updates the durable counter after each completed photo.
The deployment drain can preserve this job at the same queue boundary as a scan.
Other started jobs remain excluded from image replacement.

## 2026-11-02 — Deploy during an active scan

A photo scan stores each pending group in the PostgreSQL ORM queue.
Completed group counters plus queued scan groups must equal the scan target.
The deployment verified this invariant before replacement.
It compared 62 pre-existing table fingerprints across the offline migration.
The same scan continued after startup. See `docs/validation/remote-ai-deployment.md`.

A direct queue cluster `SIGTERM` can deadlock during worker recycling.
The sentinel first stops the pusher. A full queue can block the pusher.
A recycled worker then leaves the stopping sentinel with no consumer.
Do not kill the application to resolve this state while a worker is active.

Options considered: wait for the complete scan, stop the container immediately,
or drain prefetched tasks while the sentinel still replaces workers.
The owner authorized a temporary pause. The drain preserves durable progress.
The helper suspends the pusher, drains leased task IDs, then stops the cluster.
It renews captured leases while workers finish. It refuses ambiguous processes.
A real isolated queue exercise passed with frequent worker recycling.
The helper depends on Linux `/proc` and the current queue process layout.
Keep that layout check and the isolated exercise when queue dependencies change.

## 2026-11-01 — Remote AI implementation

The owner authorized issues #1 and #2 for implementation.
The accepted design is in `docs/plans/01_remote-ai-providers.md`.
Captioning uses the Chat Completions image input contract.
The existing caption prompt and context pass through unchanged.
The provider must return final text in `choices[0].message.content`.
Sources: <https://developers.openai.com/api/docs/guides/images-vision> and
<https://developers.openai.com/api/reference/resources/chat/methods/create>.

The GX10 image gateway accepts image data URLs in `/v1/embeddings`.
This is a local extension of the OpenAI text embedding schema.
SigLIP2 NaFlex returns 1152 values. Its native aspect ratio and patch budget
must be preserved. Text queries and image vectors must use the same profile.
Sources: `Admin/gx10/docs/inference/image-embeddings.md`,
<https://huggingface.co/google/siglip2-so400m-patch16-naflex>, and
<https://huggingface.co/docs/transformers/model_doc/siglip2>.

Options considered: replace the legacy columns in place, or add separate
remote caches and index namespaces. Separate caches were selected.
They use more disk space. They preserve the working index during conversion.
The fingerprint includes preprocessing and checkpoint revision.
Credentials and score thresholds do not change vector identity.
A checkpoint revision change behind the same model handle cannot route text
queries to the earlier weights. Pause text semantic search in that case.
Keep metadata search and cached image similarity available until promotion.
Saved credentials use the existing encrypted database field integration.
Only administrators can read the non-secret connection settings.

A cancelled or failed run reuses completed batches in the next run.
The existing job claim guard prevents duplicate task delivery.
It does not automatically resume an already-started job after a process dies.
Keep that guard. Cancel an interrupted job, then start a new build.
This avoids concurrent activation from duplicate deliveries.

Cosine thresholds are initial settings, not measured quality guarantees.
No representative retrieval or label-quality benchmark has been completed.
The unchanged deployed AMD64 image fails three face EstimateNorm precision
tests under the Mac Docker emulator. Maximum absolute differences are about
2e-6 to 7.5e-6 against a 1e-12 test tolerance. This is baseline evidence.
The remote provider implementation does not change face alignment.

## 2026-11-01 — PhotoLibrary mount migration

The owner selected `/data/PhotoLibrary` as the container mount target.
The host mount remains `/mnt/librephotos`. The NAS directory stays unchanged.
`PHOTOS` and `DATA_ROOT` remain `/data`. The admin scan directory is now
`/data/PhotoLibrary`. This leaves room for separate sibling library roots.

A rescan can relink unchanged files by content hash. It can repeat file reads.
A prefix migration preserves existing rows and avoids that relinking pass.
The active scan also contains pickled User objects and signed path arguments.
The migration therefore rewrote catalog paths and queued scan tasks together.
It retained queue IDs, leases, job IDs, and progress. It refreshed derived
search captions from the existing metadata. Historical job errors retain the
paths recorded when those errors occurred.

The app stopped before the backup and migration. PostgreSQL stayed running.
Recovery files are in
`/srv/librephotos/backups/remount-photolibrary-20261101T174331Z` on docker-srv.
They include a verified database dump, a preview/model archive, the previous
Compose file, and a private environment snapshot. Do not publish that directory.

The transaction compared fingerprints for all 61 API tables, including their
membership tables. It normalized only the intended path fields. It excluded
only the two regenerated search fields. The comparison preserved all other
values, including photo IDs, embeddings, captions, faces, and the password hash.
It also verified 26,894 queued task payloads, 21,794 protected-media files,
and SHA-256 samples of 12 originals. No inference or image rebuild was needed.

After restart, health, login, photo details, thumbnails, and original downloads
returned HTTP 200. The downloaded original matched its stored file SHA-256.
The photo count increased from 7,256 to 7,285. The same scan job continued at
8,476 of 35,274 groups. The database container and application image were retained.

The first helper attempt failed on a Python import path before any catalog
change. The rollback guard restarted the previous configuration. The corrected
helper passed a read-only serialization check before the successful retry.

## 2026-11-01 — Docker-srv deployment

The user selected docker-srv and requested frequent image rebuilds.
The Mac checkout is the build source. Docker-srv runs AMD64 images.
External downloads from Docker Hub, GitHub releases, and Yarn fail on docker-srv.
Build images on the Mac and publish them to the LAN registry.
Use the official npm registry for the build. Preserve lockfile integrity checks.
Keep revision metadata after the dependency and frontend layers.
A second build reused both dependency installation and the frontend build.
Store models outside the image. Preload the checksum-verified default face model
through the Mac because its upstream GitHub release is blocked on docker-srv.
The NAS media share has SMB access. PhotoLibrary is a read-only subdirectory bind
into CT 100 and the application. The NAS folder layout was preserved.
The user approved PhotoLibrary only. Scans is outside this deployment.

## 2026-11-01 — Fork selection and source review

The review used release `1.5.1` at
`2097ce7b44a318039c68997816bc91d85da3ea31`.

LibrePhotos was selected over PhotoPrism for the complete required workflow.
It already provides image embeddings, an image similarity index, face search,
duplicate review, caption storage, and directory move operations.
Adding caption providers can use the existing service boundary in
`apps/backend/api/classification/captioning.py`.

### Reproduced filesystem findings

- Concurrent moves to one destination can overwrite a file.
  `_move_on_disk` checks existence and then calls `shutil.move`.
  A competing destination can appear between these operations.
- An interrupted cross-filesystem move can leave a partial destination.
  The helper records the destination for rollback only after the copy succeeds.
  The original fixture remained intact in the isolated reproduction.

Both findings concern `apps/backend/api/photos/files.py`.
They were reproduced with temporary files in the source review.
They remain unresolved in this initial fork.

### Feature limits

- The current captioner is LFM2.5-VL-450M in a local sidecar.
- Generated captions use `captions_json["im2txt"]`.
- The metadata writer exports `user_caption`. It excludes generated captions.
- The main semantic search filter does not preserve similarity order.
- Duplicate suggestions use path length or image resolution.
- General blur and aesthetic quality assessment requires a new workflow.

Quality assessment requires more than model execution.
It also needs score storage, model provenance, filters, and review controls.

### Validation scope

The source review exercised isolated filesystem helpers.
It did not deploy the application or evaluate model accuracy.
The fork initialization changes documentation only.

### Repository transfer

An initial GitLab server-side import failed during cloning.
The Mac fetched all upstream branches, tags, and history.
The owner then selected a native GitHub fork and removed the publishing prohibition.
The development branch is published to the personal GitHub fork.

The live gateway smoke used a temporary synthetic 640x320 JPEG.
The new embedding client returned normalized 1152-dimensional vectors.
The matching description scored 0.2119. An unrelated description scored -0.0337.
The caption client used the resident `qwen3.5-9b-nvfp4` model with the optional
vLLM thinking flag disabled. It described the red square and blue circle correctly.
No production photo or persistent application setting was used in this check.

The Mac Docker VM has about 2 GiB RAM. Concurrent emulated checks caused timeout
failures and killed the documentation build. Native Node 24.22.1 with verified
platform bindings completed the focused UI tests and documentation build.
The docs build reports an existing `#public-gallery-user` anchor warning.

The original docker-srv scan was still active during implementation validation.
It had indexed 22,830 photo rows and processed 24,306 of 35,274 groups.
The production image was retained. The implementation does not change the
running provider selection or start a full remote reindex.

The full repository checks also found a pre-existing Docker image guard failure.
The docker-srv Dockerfile used ARG values for its FROM images.
The guard does not resolve complete image references from ARG values.
The Dockerfile now names the same pinned image digests directly.
The immutable base images and cache behavior remain the same.

The standalone smoke checker previously required the tags sidecar to run.
The tags sidecar is optional when all active libraries use remote embeddings.
The smoke checker now treats the tags sidecar as optional.
Remote captions record their provider, model name, and source image hash.
They do not store tokens or endpoint URLs in photo metadata.
