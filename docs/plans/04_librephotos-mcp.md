# LibrePhotos MCP adapter

Date: 2026-11-02
Issue: https://github.com/s1mb1o/librephotos/issues/4
Dependency: `codex/permanent-api-keys`, issue #3.

## Requirements and design

Use the official MCP Python SDK in a separate service. Support stdio and
Streamable HTTP. Use REST only. Do not mount photos or access the database.
Use a permanent LibrePhotos API key for stdio. For shared HTTP, validate OAuth
access tokens against an external issuer, a configured JWKS URL, and the MCP
resource audience. Require expiry, issuer, subject, audience, and MCP scope.
Map each subject to a separate LibrePhotos key in a protected credentials file.
Never forward the MCP bearer token as the LibrePhotos credential.
Use SDK protected-resource discovery and authorization middleware.

Add bounded backend search, similarity, photo-detail, album-photo, and job-status
reads. Reuse existing filters, visibility rules, sharing redaction, similarity
services, and job ownership. Preserve relevance order. Page SQL querysets before
serialization. Cap semantic candidates and page size. Do not change legacy clients.
Return stable photo UUIDs. Hide filesystem paths from MCP results.
Stream previews through authenticated media routes. Limit their byte size.
Reject external URLs and redirects. Bound JSON responses and validate DTOs.
Treat photo metadata as untrusted content. Keep credentials out of errors and logs.

Register read tools by default. Register metadata, user-album, scan, and caption
job tools only when writes are explicitly enabled. Existing API-key scopes and
LibrePhotos ownership rules MUST still authorize each request.
Return job identifiers immediately. Never wait for a scan or caption batch.

## Validation

Test tool discovery and calls with the official SDK over both transports.
Test subject isolation, expired tokens, wrong audiences, missing scopes, denied
objects, invalid identifiers, result bounds, pagination, previews, redacted errors,
timeouts, malformed upstream responses, and disabled writes.
Run backend regression and static checks. Build the standalone Docker image.
Request a Claude Opus 5.5 xhigh review and resolve actionable findings.
Commit and push a branch stacked on the API-key branch.
