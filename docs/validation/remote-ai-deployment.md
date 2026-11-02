# Remote AI deployment validation

Deployment: 2026-11-01, 20:39 UTC.
Follow-up validation: 2026-11-02, Europe/Moscow.
Host: `docker-srv`, `192.168.86.16`.
Application URL: <http://192.168.86.16:19850>.
Source: `eadec7938a905ecd01146b9660483959e7579d31`.

## Image and recovery checkpoint

Image: `registry.my.3simbio.ru/librephotos/app:20261101T202714Z-eadec7938a90`.
Manifest digest: `sha256:89e5b235dd428dc3834cf61ac6f4f8f204520a9f757a91d5e1c09bf20798976e`.
Previous image: `registry.my.3simbio.ru/librephotos/app:20261101T164012Z-3fe531755ed3`.

Private recovery directory on docker-srv:
`/srv/librephotos/backups/deploy-20261101T203948Z`.
The directory contains the frozen PostgreSQL dump, previous Compose file,
private environment, checkpoint helper, and verification receipts.
The dump SHA-256 is
`e9fec412bc858db0a6c5cd24d76987bdeb69e8a66ce835de517621d9f83e4b17`.
`pg_restore --list` accepted the dump.
The environment and dump have mode `0600`. The directory has mode `0700`.
Do not publish these recovery files.

## Preserved scan and catalog

The scan retained job ID `6edb6684-3657-4e38-8291-6770e3cf4bfd`.
Its start time stayed `2026-11-01 16:46:28.809929+00:00`.
At the frozen checkpoint, the scan had completed 30,120 of 35,274 groups.
Exactly 5,154 scan tasks remained. The catalog contained 28,509 photos.
The queue also contained 66 maintenance tasks.

Migration `api.0221_remote_model_providers` ran before workers started.
All original fields and rows matched across 61 API tables and `django_q_ormq`.
This comparison included metadata, captions, faces, vectors, passwords,
scan counters, and signed queue payloads.
The helper released 51 stale leases after the old cluster stopped.
The helper did not replace queue payloads or reset scan counters.
The same scan advanced to 30,128 immediately after startup.
A later read-only check reported 31,225 completed groups and 29,510 photos.
The scan had no failed or cancelled flag.

The PostgreSQL container ID stayed unchanged.
Persistent cache, log, and protected-media mounts stayed unchanged.
The original photo mount remained read-only at `/data/PhotoLibrary`.
Sampled original and thumbnail SHA-256 values matched before and after startup.

## HTTP and provider checks

Readiness, Admin Area, authenticated settings, photo details, a thumbnail,
and an original returned HTTP 200.
The original HTTP bytes matched the NAS file SHA-256.
An existing caption remained unchanged.
Admin settings included the new remote provider fields.
Saved tokens were absent from responses.
Anonymous users could not read private connection settings.

Captioning remained `lfm2_vl_450m`.
Embeddings remained `openclip_vitb32`.
The selected and active embedding models matched.
No rebuild was required. Text semantic search remained available.
This deployment did not start a remote reindex or change provider selection.

## Queue drain finding and regression exercise

The first graceful shutdown exposed a django-q2 recycling deadlock.
The pusher waited for space after the worker recycled.
The stopping sentinel no longer replaced that worker.
Recovery verified that no worker remained and that all scan tasks were durable.
Only idle cluster processes stopped. The checkpoint then preserved the queue.

The revised helper suspends the pusher before it stops the sentinel.
Workers finish prefetched tasks while the sentinel can replace recycled workers.
The helper then resumes the pusher for normal cluster shutdown.

An isolated container tested the revised helper with a real ORM queue.
The container had no network and no production mounts.
One worker recycled after each two tasks. The prefetch limit was six.
The helper paused at 8 of 20 tasks with exactly 12 tasks still queued.
The same job resumed and completed all 20 tasks.
Nine worker recycling events occurred. No task was lost.
See `deploy/docker-srv/tests/README.md` for reproduction.
The revised drain was not tested by pausing the live scan again.

The helper requires Linux `/proc` and the current Python 3.14 queue process layout.
The regression exercise covers the deployed single-worker configuration.
A started monolithic job must finish before an image replacement.
