# LibrePhotos personal fork

Created: 2026-11-01

This fork supports a personal photo library in existing NAS directories.
Its intended extensions cover configurable caption models, semantic search,
photo quality assessment, and directory organization.

## Repository identity

- Fork: <https://github.com/s1mb1o/librephotos>
- Upstream: <https://github.com/LibrePhotos/librephotos>
- Development branch: `codex/nas-photo-library`.
- Reviewed upstream release: `1.5.1`.
- Base commit: `2097ce7b44a318039c68997816bc91d85da3ea31`.
- Mac development checkout: `/Users/ashmelev/Productivity/librephotos`.
- Retained NAS checkout: `/Volumes/projects/librephotos`.
- The same project share is mounted at `/mnt/projects` on GX10.

The fork preserves the available upstream branches, tags, and full history.
The development branch starts from the reviewed stable release.
Application code is unchanged at fork initialization.
The inherited license and attribution remain in place.

## Git workflow

`origin` is the personal GitHub fork.
`upstream` is the public GitHub repository for fetches.
The local upstream push URL is disabled.

Agents MAY commit and push to GitHub or GitLab when the user authorizes the task.
Agents MUST inspect the actual push URL before each push.
Use `codex/` for new development branches unless the user specifies another name.

Keep upstream branches available for comparison.
Review upstream changes before merging them into the development branch.
Keep each change focused to reduce future merge work.

## Initial priorities

1. Make destination publication refuse concurrent overwrites.
2. Recover safely from interrupted copies between filesystems.
3. Add configurable local and remote caption providers.
4. Add cached technical and aesthetic quality scores.
5. Group similar photos and rank review candidates by quality.
6. Preserve semantic relevance in search results.
7. Add explicit caption acceptance and XMP export workflows.

See [ResearchLog.md](ResearchLog.md) for the reviewed limitations.
See [SMOKE_TESTS.md](SMOKE_TESTS.md) for validation targets.
Fork creation did not implement these priorities. Remote captioning and
SigLIP2 NaFlex inference are now implemented. Quality scoring and directory
organization remain future work. See `apps/docs/docs/user-guide/settings/remote-ai.md`.

## Original photos

Use read-only photo access for the initial deployment trial.
Keep generated previews and catalog state on writable storage.
Use temporary fixtures for filesystem tests.
Keep scores from a model separate from manual ratings.
Record the producing model and image identity for derived results.

## Automation

GitHub Actions are disabled for this initial fork.
The inherited workflow files remain available for later review.
No application was deployed during fork creation.

## Local deployment

LibrePhotos runs on `docker-srv` at `http://192.168.86.16:19850`.
Use `deploy/docker-srv/deploy.sh` on the Mac to build and deploy changes.
Read `deploy/docker-srv/README.md` for state, credentials, and rollback.
The deployment uses read-only access to `media/personal/PhotoLibrary`.
The NAS source checkout is retained. The deployment builds from the Mac checkout.
