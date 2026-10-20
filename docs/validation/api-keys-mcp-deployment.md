# API-key and MCP deployment validation

Date: 2026-11-02

## Source integration

The deployment combines API keys, MCP, and the deployed model-settings Test action.
The integration branch is `codex/deploy-api-keys-mcp`.
The source checkout is isolated from the other development thread.
The owner selected persistent MCP HTTP tokens and prohibited Claude reviews.
No external review was requested or performed for this deployment.

## Pre-deployment checks

- Backend search, authentication, sharing, model checks, migration, and deployment rules: 437 tests passed.
- Backend Ruff, formatting, types, dead-code, import contracts, and schema generation passed.
- MCP protocol, OAuth compatibility, persistent-token identity, revocation, and bounds: 26 tests passed.
- A real non-root AMD64 container accepted a persistent token and exposed nine read tools.
- The container rejected anonymous requests and rejected the token immediately after verifier removal.
- API-key and model-settings UI tests: 15 passed.
- Shared API-client tests: 492 passed. Nine live tests were skipped.
- Frontend and end-to-end TypeScript checks passed. Full frontend lint passed after the isolated checkout received its end-to-end dependencies.
- Documentation build passed with the existing public-gallery anchor warning.

## Deployment targets

- Application: `http://192.168.86.16:19850`.
- MCP: `http://192.168.86.16:19851/mcp` on the LAN.
- MCP authentication: separate high-entropy persistent bearer tokens.
- MCP account access: scoped read-only LibrePhotos API key.
- MCP client secret reference: macOS Keychain item `librephotos-mcp-docker-srv`, account `ashmelev`.

The application deployment uses the existing queue drain and frozen catalog backup.
The MCP deployment mounts only its protected credentials directory.
It does not mount photos or access PostgreSQL directly.
Post-deployment receipts and live checks are recorded after activation.

## Deployed images and recovery

- Application source revision: `c7c165ac849c`.
- Application image: `registry.my.3simbio.ru/librephotos/app:20261102T022434Z-c7c165ac849c`.
- MCP image: `registry.my.3simbio.ru/librephotos/mcp:20261102T022758Z-c7c165ac849c`.
- Recovery checkpoint: `/srv/librephotos/backups/deploy-20261102T022513Z/`.
- All 66 pre-existing catalog and queue tables matched their frozen fingerprints.
- The catalog retained 32,166 photos. The database container was preserved.
- No active scan or queued photo work existed before deployment.

## Live checks

The application, database, and MCP containers report healthy.
JWT sign-in and API-key creation, verifier-only responses, authenticated media,
read-only restrictions, credential-management restrictions, and immediate revocation passed.
The temporary verification keys were revoked. Photo metadata was not changed.

An official SDK client discovered nine read tools through the deployed HTTP endpoint.
Photo search, semantic search, similarity, detail, WebP previews, people, MD5 lookup,
and owner-scoped job status passed. No user albums exist, so the live album list is empty.
Actual album contracts remain covered by the backend and adapter tests.
An extra temporary MCP token was accepted, then refused after its verifier was removed.
The primary token remained valid. The credentials directory bind is read-only.
Only port 19851 on `192.168.86.16` is published for MCP. No WAN route was added.

A fresh headless browser signed in and loaded Settings > API Keys.
The provisioned read-only key was visible. No browser runtime error occurred.
No secret was placed in a screenshot, source file, URL, or deployment log.
The raw MCP client token is referenced by its macOS Keychain item.
