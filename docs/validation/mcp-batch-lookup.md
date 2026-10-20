# Batch MCP file lookup validation

Date: 2026-11-06.
Application and MCP revision: `22c44b2624bf`.

## Checks

- 109 selected backend tests passed. They cover the one-query limit, matching rules, and account scope.
- Backend lint, type checks, import rules, dead-code checks, and OpenAPI validation passed.
- 28 MCP tests passed. They cover one upstream request, input limits, and response validation.
- MCP lint, formatting, and type checks passed.
- API client types and lint passed. The suite passed 494 tests and skipped 9.
- The documentation build passed. It reported the existing `#public-gallery-user` anchor warning.
- A synthetic folder test split 205 distinct digests into batches of 100, 100, and 5.
- A simulated failure left the failed and unsent batches unchecked.

## Deployment

Application image: `registry.my.3simbio.ru/librephotos/app:20261106T085752Z-22c44b2624bf`.
MCP image: `registry.my.3simbio.ru/librephotos/mcp:20261106T090041Z-22c44b2624bf`.
Recovery checkpoint: `/srv/librephotos/backups/deploy-20261106T085833Z`.

The queue was empty before the application restart.
No database migration was required. All 67 catalog and queue tables passed verification.
The catalog retained 32166 photos. The same PostgreSQL container remained in service.
Application readiness returned HTTP 200. Both containers reported healthy.
The existing MCP credential mapping was retained.

The live MCP service listed 10 read tools. The single-file lookup returned the original photo ID.
A 100-digest batch returned ordered results with uppercase input, duplicate digests, and misses.

## Folder timing

The before and after checks used the same 93 files and the same account.
Each timing includes process startup, file reads, hashing, and MCP requests.
The previous script used four concurrent requests and 93 lookup calls.
The batch script used one lookup call. Every result and photo UUID matched.

| Version | Runs in seconds | Median in seconds |
| --- | --- | ---: |
| Previous script | 7.383, 6.831, 7.843 | 7.383 |
| Batch script | 1.554, 0.441, 0.435 | 0.441 |

The batch median was 16.7 times as fast in this check.
Local file caches and server load affect timing.
The installed skill and script passed a final live check with all 93 matches.
