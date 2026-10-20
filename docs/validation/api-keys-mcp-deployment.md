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
- Frontend and end-to-end TypeScript checks passed.
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
