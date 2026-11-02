# Backend contract fixtures

`backend.json` contains synthetic authenticated Django REST responses.
`api.tests.search.mcp_contracts.collect_mcp_contracts` generates these responses.
The helper creates test users, scoped API keys, photos, albums, shares, and a job.
The helper retrieves a generated WebP through the authenticated media endpoint.
It does not use production photos or credentials.

Run the helper inside a fresh `DiscoverRunner` test database.
Use `librephotos.settings.test_sqlite` and temporary media paths.
Serialize the returned dictionary as JSON to this file.
Never run this fixture generator against a production database.

The fixture covers owner reads and library, album, contributor, and person shares.
It includes denied metadata grants, metadata writes, and UUID-based album additions.
The adapter tests validate the actual response shapes and decode the preview bytes.
