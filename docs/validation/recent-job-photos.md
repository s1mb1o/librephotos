# Recent caption job results validation

Date: 2026-11-02.
Feature branch: `codex/recent-job-photos`.
Base revision: `464b8c6d9`.
Deployment status: Pending.

## Behavior

Generate Captions job pages show the latest 20 processed photos.
Each result has a preview, caption snapshot, status and processing time.
The preview opens the photo page. The list refreshes while the job runs.
The feed reports completion with the final recorded results.
Existing completed work is not backfilled. Recording starts after deployment.

The snapshot records the caption returned by this processing attempt.
A later manual caption edit does not change the snapshot.
A repeated attempt replaces the same photo within the window.
Captions have an 8192-character limit. The UI marks shortened text.

The new endpoint permits only the job owner.
It excludes deleted, removed, trashed and transferred photos.
The private field does not enter existing job or queue responses.
The existing API-key policy excludes this browser endpoint.
The read endpoint does not run inference.

## Local checks

All fixtures use synthetic photos and mocked model output.
No test started inference or accessed the NAS photo library.

- Backend: 220 selected tests passed. Coverage includes snapshot retention,
  retry replacement, stale-worker merging, cancellation, progress, final output,
  ownership, API keys, query counts, schema contracts and migration consistency.
- Backend static checks passed: Ruff checks and formatting, the unchanged Ruff
  baseline, mypy, dead-code checks and all five import contracts.
- OpenAPI generation is current and produced no schema reports.
- New frontend component and job-detail tests: 12 passed.
- Frontend ESLint, TypeScript, end-to-end TypeScript, Knip and formatting passed.
- Frontend production build passed.
- API client: 494 tests passed and 9 skipped. TypeScript and ESLint passed.
- Mobile: 549 tests passed in 67 suites. TypeScript and ESLint passed.
- Documentation build passed.

The full frontend suite had 4416 passes, 2 failures and 9 skips.
Both failures also occur on the unchanged base revision in a separate worktree:

- `src/architecture/forms.test.ts` rejects the existing `ApiKeysCard.tsx` form state.
- `src/components/settings/Settings.dateRulesOffer.test.tsx` selects an empty
  status element instead of the date-rule notice.

This feature does not change those settings files or suppress the failures.
The docs build reports an existing settings public-gallery anchor warning.
The frontend build reports an existing large map chunk warning.
The mobile runner reports an existing worker-exit warning after passing tests.

## Deployment procedure

Use `deploy/docker-srv/deploy.sh` after committing the feature.
The helper drains prefetched caption tasks with the pending-task lease barrier.
It backs up frozen PostgreSQL state before migration 0223.
It compares all pre-existing API and queue fields after migration.
It must resume the same caption job with its original start time and target.
Keep the PostgreSQL and MCP containers and the read-only photo mount unchanged.
Verify the authenticated page and observe new results from the existing job.
Do not start an additional caption job for verification.
