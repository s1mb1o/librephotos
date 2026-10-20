# Permanent API-key validation

Date: 2026-11-02
Issue: https://github.com/s1mb1o/librephotos/issues/3
Base: e270018cb9d6d544f9db16d4ffa27d36d99c5156

## Review

Claude Code used `claude-opus-5-5` with `--effort xhigh`.
The user authorized submission of all required source context.
The first review identified administrator-key isolation and lifecycle concerns.
The second review reported no blocking defect. Its remaining recommendations
were addressed with expiration validation, immediate secret display, lifecycle
tests, explicit sharing documentation, and successful media/search tests.
API keys cannot use a JWT cookie to bypass upload restrictions.

## Checks

- Backend conventions, ownership, migration synchronization, media and queue access: 116 tests passed before review hardening.
- API-key tests cover administrator isolation, positive scopes, secret redaction, JWT compatibility, owner deletion, cookie fallback, key limits, revocation time, and last-used write limits.
- Shared API-client suite: 490 passed, 9 skipped. Live tests require a configured backend.
- Account UI and expiration tests passed. The one-time secret survives an Escape key press.
- Frontend and shared-client TypeScript, lint, and unused-code checks passed.
- Frontend production build and documentation build passed.
- Backend type checking reports zero errors. Schema generation and lint pass.
- Mobile type checking and lint passed. Its suite passed 545 tests and failed four viewer tests.

## Existing failures

The same four `PhotoViewerScreen.test.tsx` failures reproduce on the unchanged
base commit in a separate temporary checkout. They report
`TypeError: window.dispatchEvent is not a function`. This change does not modify
mobile code. The documentation build retains the existing `#public-gallery-user`
broken-anchor warning.

## Isolation

All work used a temporary clone. Test containers had temporary data paths and
no NAS mount. No production scan, database, or deployment was changed.

The broader MCP regression group exposed a naming-guard false positive.
The guard applied JSON snake_case rules to the standard `Authorization` header.
The guard now excludes HTTP header names. It still checks JSON properties and query parameters.
