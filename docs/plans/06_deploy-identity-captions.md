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
Use the existing pusher suspension and worker drain at task boundaries.
Add only JOB_GENERATE_CAPTIONS to the existing drainable job types.
Require completed items plus queued items for that job to equal its target.
Do not permit other started job types.
Test a caption job with real ORM queue workers and worker recycling locally.
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
