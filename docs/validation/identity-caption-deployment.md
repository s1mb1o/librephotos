# Identity-aware caption deployment

Date: 2026-11-02.
Service: http://192.168.86.16:19850.
Source branch: codex/deploy-identity-captions.
Application revision: 1680406af0f2.
Host deployment helper revision: d1bdbd7d3.
Issue: https://github.com/s1mb1o/librephotos/issues/8.

## Active image

```text
registry.my.3simbio.ru/librephotos/app:20261102T070136Z-1680406af0f2
sha256:78f3be00c1eea42bf38245a137001ae82df2e153a041d57a4c011f1e8611f9c8
```

The image combines identity-aware captions with the deployed API-key and MCP code.
The model Test action, providers and semantic settings remain available.
The host helper correction does not change application image contents.

Previous image:

```text
registry.my.3simbio.ru/librephotos/app:20261102T022434Z-c7c165ac849c
```

## Preserved job

Job: e62cd637-6b8d-4227-a050-a1623eb83f09.
Type: Generate Captions.
Original start: 2026-11-02 06:47:10.720443 UTC.
Target: 32089.

The corrected drain began at 712 completed photos.
It finished all 52 taken tasks before stopping the application.
The frozen state had 764 completed photos and 31325 pending photo tasks.
Their sum equals the original target.
All 31409 queued tasks, including maintenance work, remained durable.
The same job resumed at 765 and reached 840 during verification.
Its ID, target and start time stayed unchanged. It was not cancelled or failed.
The authenticated post-update job response reported zero photo errors.

## Data and recovery

The catalog retained 32166 photos.
All 67 pre-existing API and ORM queue table fingerprints matched after the offline check.
No database migrations were needed.
The database container and MCP container retained their original identities.
The original mount remained read-only at /data/PhotoLibrary.
Generated-media samples passed the checkpoint hash checks.

The private recovery checkpoint is on docker-srv:

```text
/srv/librephotos/backups/deploy-20261102T072826Z/
```

It contains the verified PostgreSQL dump, private environment snapshot,
frozen table fingerprints, media samples and activation receipts.
Keep the environment snapshot and dump private.
Follow deploy/docker-srv/README.md for rollback.

## Checks

- 131 combined caption, API-key, integration, sharing and query-count tests passed.
- Backend lint, formatting, baselines, types, dead code, imports and API schema passed.
- The merged docs built. An existing settings-page anchor warning remains.
- All supported pause types passed an isolated 80-task exercise.
- Each exercise began with 52 leased tasks, used 64 KiB arguments and recycled workers.
- A forced timeout preserved the old cluster and released deferred work.
- An enqueue during the pause survived and completed after resume.
- Readiness returned HTTP 200 after replacement.
- The same MCP token reached all nine read tools.
- Authenticated photo search returned the same visible count before and after: 32165.
- Authenticated job reads retained the original ID, start time and target.
- The identity signal module and server-side template renderer passed live checks.
- The new job stored 76 caption records with identity metadata during verification.

## Real-model limitation

In that sample, 45 captions had supplied face boxes.
One template contained a face reference. No resolved personal name was observed.
The earlier 46-item sample had four photos with currently eligible identities.
These samples verify the live request and storage path.
They do not establish correct face-to-action grounding or reliable named output.
The configured model often omits the requested references.
Keep the issue's real-model evaluation task open.

## Queue correction

The first activation stopped before replacement.
Suspending the pusher also suspended its feeder thread during a partial pipe write.
Interrupting only the maintenance helper resumed the old job.
The old schema and image remained active during that correction.

The current helper leases available ORM rows instead of suspending the process.
The feeder and worker replacement continue until taken tasks finish.
Temporary leases are released after shutdown or when the drain fails.
Task payloads, queue keys and job counters are not rewritten by this barrier.
A lease expires normally if the maintenance process cannot run its cleanup.

## Local evidence

```text
/Users/ashmelev/Documents/ChatGPT/Housekeeping/photo-source-review/identity-deployment-20261102/
```

Use deploy-retry.log, combined-regression.log, docs-build.log,
lease-pause-*-final.log, mcp-before.json, mcp-after.json and
live-verification-final.log. deploy.log records the recovered first attempt.
