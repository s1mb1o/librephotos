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
- Canonical Mac checkout: `/Volumes/projects/librephotos`.
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
These priorities are pending. Fork creation does not implement them.

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
