# Model settings Test validation

Date: 2026-11-02.
Branch: `codex/remote-ai-providers`.

Test uses draft remote settings and a temporary synthetic JPEG.
It validates caption text or both image and text embedding vectors.
It does not save settings, change the selected model, queue a job, or rebuild an index.
A blank token reuses the saved token. Clear saved token tests without authentication.
The API returns no token or provider response text.
The UI hides a result after draft values change or the settings save.

## Checks

| Check | Result |
| --- | --- |
| Backend provider checks, remote clients, authorization, URL rules, and tenant guards | 115 passed |
| Model UI, translations, forms, errors, and polling checks | 28 passed |
| Shared API-client and OpenAPI contract suite | 489 passed; 9 skipped |
| Mobile types, lint, and tests | Pass; 549 tests passed |
| Frontend types, e2e types, full ESLint, formatting, and Knip | Pass |
| Frontend production build | Pass |
| Backend Ruff, formatting, baseline, mypy, dead code, and import contracts | Pass; zero type errors; five contracts kept |
| API schema generation | Pass; stable RemoteModelKindEnum; no new reports |
| Documentation production build | Pass |
| Local queue pause/resume for photo scans and tag generation | Both passed; pause at 8/20 and resume to 20/20 |

Backend checks ran in a local container with no network or production mounts.
The queue exercise used one worker, a prefetch limit of six, and recycling after two tasks.
Each job retained exactly 12 queued tasks at the pause.
Each job completed all 20 tasks after resume. Nine worker recycles occurred per exercise.

The documentation build retains the existing `#public-gallery-user` anchor warning.
The mobile suite reports existing asynchronous cleanup warnings after passing.
These checks do not measure model quality.

## Deployment

Built image: `registry.my.3simbio.ru/librephotos/app:20261101T212901Z-a365b8741c4d`.
Manifest digest: `sha256:5e319b46fd35c48cc01a4286060d5a98d980e959ed7e164959cf4af73186418a`.
Application commit: `a365b8741c4d`.

The first activation refused a started embedding calculation before any queue pause.
The original application remains healthy. No processing progress was reset.
A one-time waiter will activate the built image after other started jobs finish.
Its process ID at launch was `1428144` on docker-srv.
It checks every 30 seconds and refuses to replace a different selected image.
It stops with a recorded failure if processing is still active after 24 hours.
It does not cancel jobs or release their leases while it waits.

Runtime waiter: `/srv/librephotos/bin/deploy-model-test-20261102.py`.
Status: `/srv/librephotos/backups/model-test-deployment-pending.json`.
Log: `/srv/librephotos/backups/model-test-deployment-wait.log`.
After activation, the waiter checks both model test paths with an ephemeral loopback provider.
That check sends only synthetic input and compares saved settings and active index state.
Live HTTP verification is pending until activation.
The original photo scan completed while this update was in validation.
Automatic per-photo tag generation is now covered by the verified deployment drain.
Other started jobs still prevent container replacement.
