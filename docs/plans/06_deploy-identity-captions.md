# Deploy identity-aware captions

Date: 2026-11-02.
Status: Preflight passed. Activation is pending. The owner authorized deployment and a temporary job pause.

## Requirements

Preserve the API-key and MCP deployment at c7c165ac849c.
Integrate the identity-aware caption branch without removing newer features.
Keep the database, original mount, previews, credentials and MCP container.
Preserve the running Generate Captions job and its start time and counters.
Do not cancel or restart that job from zero.

## Pause method

Caption generation queues one durable task per photo.
Each task acknowledges one completed item through update_scan_counter.
Use temporary ORM leases to stop new dequeues while the feeder thread continues.
Do not suspend the pusher process. Suspension can freeze a partial pipe write.
Refresh the temporary leases during the drain. Release them on success or failure.
Add only JOB_GENERATE_CAPTIONS to the existing drainable job types.
Require completed items plus queued items for that job to equal its target.
Do not permit other started job types.
Test all supported jobs with 50 prefetched tasks, 64 KiB task arguments,
worker recycling, and an enqueue during the drain.
Use synthetic tasks in a container without production mounts or network.

## Activation

Build and push a unique AMD64 image through the existing deployment command.
Pull the image before maintenance.
Drain tasks. Stop only the application after workers finish.
Back up frozen PostgreSQL state and verify the dump.
Compare all old API and queue table fingerprints before workers restart.
Resume the same job and verify forward progress.
Verify readiness, authenticated media, API keys, MCP and the new caption code.
Keep the prior image and matching checkpoint for recovery.

## Preflight results

Scan, tag and caption pause exercises each passed with real queue workers.
Each exercise paused at 8 of 20 items and resumed to 20 of 20.
Each exercise observed nine worker recycling events.
The combined source passed 131 caption, API-key, integration and sharing tests.
Lint, format, baseline, types, dead-code, import and schema checks passed.
The merged documentation build passed with an existing unrelated anchor warning.
Authenticated MCP search and the running caption job were reachable before deployment.

## Corrected pause method

The first activation stopped before application replacement.
SIGSTOP also suspended the pusher's multiprocessing feeder thread.
The worker then waited for a partial queue message at a larger prefetch size.
The maintenance helper was interrupted. Its cleanup resumed the pusher.
The same caption job advanced again. The old image and schema stayed active.

Use a temporary lease barrier for pending ORM rows instead.
Keep signed payloads, keys, job counters and application data unchanged.
Keep the feeder and worker replacement active until taken tasks are acknowledged.
Release barrier leases only after shutdown, or when an error restores normal work.
The normal ten-minute lease expiration remains a fallback after process failure.

## Corrected preflight results

All three supported job types passed the corrected lease-barrier exercise.
Each run observed 52 leased tasks before the pause and used 64 KiB arguments.
Each run paused at 56 of 80 and resumed to 80 of 80.
A forced timeout preserved the old cluster and released deferred tasks.
The exercise also queued a new task during the drain and observed worker recycling.
The previously built application image remains valid. Only host-side deployment
helpers, tests and documentation changed after that build.
