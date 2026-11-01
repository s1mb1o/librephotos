# Research log

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
