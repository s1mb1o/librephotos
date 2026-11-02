# MCP validation

Date: 2026-11-02
Issue: https://github.com/s1mb1o/librephotos/issues/4
Dependency: `codex/permanent-api-keys`, issue #3.

## Review

Claude Code used `claude-opus-5-5` with `--effort xhigh`.
The user authorized submission of the required source context.
The first reviews identified caption-path leakage and incorrect video summaries.
The implementation now emits sharing-redacted captions and preserves media types.
The final review reported no blocking defect.
Its remaining documentation, error-message, preview-URL, and runtime consistency findings were corrected.

## Checks

- Backend search, API keys, sharing isolation, query counts, conventions, routes, naming, and migration synchronization: 383 tests passed.
- Repository Docker, compose, environment-variable, and Python-version guards: 70 tests passed without skips.
- Adapter protocol, authentication, response bounds, failure handling, and backend contracts: 23 tests passed on Python 3.13 and Python 3.14.
- PostgreSQL 16 integration suite: 17 tests passed against a temporary memory-backed database.
- Shared API-client contracts: 490 passed. Nine live-server tests were skipped.
- Backend Ruff, format, mypy, dead-code, import contracts, and schema generation passed.
- Adapter Ruff, format, and strict mypy passed.
- Documentation production build passed. It retains the existing `#public-gallery-user` anchor warning.
- Standalone Docker image built. Its configured user is `10001:10001`. Python 3.14 matches CI.
- An official SDK client discovered nine read tools through the non-root container's stdio transport. Docker networking was disabled.
- Real HTTP CLI startup in the non-root container passed. Protected-resource metadata returned 200. An anonymous MCP request returned 401 with the discovery header.
- Compose configuration validation passed with synthetic OAuth URLs. No services were started.

## Protocol and identity

Official SDK clients exercise in-process, stdio subprocess, and Streamable HTTP transports.
HTTP tests use the actual SDK ASGI application and resource-server middleware.
They verify separate OAuth-subject credentials, RSA and EC signatures, expiry,
audience, issuer, missing scope, bounded JWKS refresh, and Host and Origin checks.
Invalid identifiers do not call the REST backend.
Writes are absent by default. Optional tools require separate API-key capabilities.
Write transport failures report an unknown outcome. Clients must check Jobs before retrying.

## Backend response contracts

The backend fixture generator calls real authenticated Django endpoints.
It creates synthetic users, photos, shares, albums, and jobs in a temporary test database.
It retrieves actual generated WebP bytes through authenticated media.
It verifies metadata changes and album UUID additions in the database.
The adapter validates these responses and consumes them through an official SDK client.
Owner, library, member-album, contributor, and person-share cases are covered.
Video summaries retain their media type. Video previews use a still image.
Foreign album additions fail. Album removals persist. Scan and caption jobs return valid UUIDs.
Disabled sharing grants remain redacted.

## Operational limits

Shared HTTP requires an externally configured OAuth authorization server.
Local stdio uses a LibrePhotos API key directly.
The Docker service has no PostgreSQL connection or photo-directory mount.
No production server, scan, NAS share, or database was changed.
The existing mobile viewer failures are documented in the API-key validation report.
