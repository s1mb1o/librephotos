# Permanent API keys

Date: 2026-11-02
Issue: https://github.com/s1mb1o/librephotos/issues/3

## Requirements

Users MUST create and revoke named keys through authenticated account settings.
The server MUST show each secret once. It MUST store only a SHA-256 verifier.
Keys MUST support no expiration and an optional expiration instant.
Each request MUST check revocation, expiration, account state, and permissions.
API keys MUST NOT manage credentials or account settings.
JWT and Basic authentication MUST retain their existing behavior.

## Design

Add an owned APIKey model with a UUID lookup identifier, verifier, permissions,
creation time, expiration time, last-used time, and revocation time.
Generate a 256-bit random secret. Accept `Authorization: Api-Key <key>` only.
Use constant-time verifier comparison. Do not cache authentication results.
Apply an explicit route and HTTP-method permission map during authentication.
Reject unlisted operations. Existing view permissions and ownership checks still apply.
Default permissions are library reads and job-status reads.
Separate metadata changes, album changes, and job submission permissions.
Do not add upload or original-file management permissions in this version.
Add API-key authentication to the custom media authentication chain.
Add paginated account-key routes and a settings card with one-time secret display.

## Validation

Test JWT compatibility, scopes, user isolation, media access, secret redaction,
expiration, revocation, deactivation, deletion, and invalid credentials.
Run backend conventions, migration synchronization, schema generation, static
checks, shared-client contracts, frontend checks, and a production frontend build.
Request a read-only Claude Opus 5.5 review at xhigh effort. Resolve findings.
Commit and push the API-key branch before the dependent MCP branch.
