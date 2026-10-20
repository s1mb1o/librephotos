---
sidebar_position: 16
---

import Since from '@site/src/components/Since';

# MCP clients

<Since version="1.6.0" />

The LibrePhotos MCP adapter exposes library tools through the official Python
MCP SDK. It runs as a separate process or Docker service. It calls the REST API.
It does not query PostgreSQL or mount photo directories.
Install the API-key changes and bounded integration endpoints before the adapter.

## Local stdio connection

Create a [read-only API key](./api-keys.md) for the LibrePhotos account.
Save it in a credentials file. Limit file access to its owner with `chmod 600`.
Install the adapter with Python 3.13 or later:

```bash
python -m venv .venv
.venv/bin/pip install -r apps/mcp/requirements.txt
.venv/bin/pip install --no-deps ./apps/mcp
```

Configure an MCP client:

```json
{
  "mcpServers": {
    "librephotos": {
      "command": "/absolute/path/.venv/bin/librephotos-mcp",
      "env": {
        "LIBREPHOTOS_URL": "http://localhost:3000",
        "LIBREPHOTOS_API_KEY_FILE": "/absolute/path/librephotos.key"
      }
    }
  }
}
```

`LIBREPHOTOS_API_KEY` is also supported. Prefer the protected file.
Diagnostics use stderr. Stdout contains only MCP protocol messages.

## Shared HTTP connection

Shared HTTP uses OAuth access tokens for the MCP resource. Configure an external
OAuth authorization server. It must support the MCP client authorization flow,
including PKCE and resource indicators. Register clients with that server when
it does not offer dynamic client registration.

The adapter validates JWT signatures through the configured JWKS URL.
JWKS refreshes are serialized and limited to one attempt per minute. Cached
keys expire after five minutes.
It accepts RS256 and ES256. Tokens must include a nonempty signing-key `kid`. It verifies `iss`, `aud`, `exp`, and `sub`.
The audience must match the public MCP resource URL. The token must contain
the `librephotos:mcp` scope. The SDK publishes protected-resource metadata and
the authorization-server URL. Expired tokens receive HTTP 401. Insufficient scope receives HTTP 403.

Create one LibrePhotos API key for each authorized account. Map exact OAuth
subjects to those keys in a protected JSON file:

```json
{
  "issuer-subject-for-alice": "lp_REPLACE_WITH_ALICES_KEY",
  "issuer-subject-for-bob": "lp_REPLACE_WITH_BOBS_KEY"
}
```

The OAuth issuer is fixed per adapter service. Subject mappings cannot be
selected by tool arguments. Each subject requires a separate key. Restart the adapter after changing the
mapping file. Key revocation takes effect immediately in LibrePhotos.
The adapter does not forward MCP bearer tokens to
LibrePhotos. Every REST request uses the mapped account key and its permissions.
Do not configure a universal administrator key for a shared service.

Set these variables:

| Variable | Value |
| --- | --- |
| `LIBREPHOTOS_URL` | LibrePhotos base URL, without `/api` |
| `LIBREPHOTOS_MCP_ISSUER` | Exact HTTPS OAuth issuer URL |
| `LIBREPHOTOS_MCP_JWKS_URL` | HTTPS JWKS URL for that issuer |
| `LIBREPHOTOS_MCP_RESOURCE_URL` | Public HTTPS resource URL, for example `https://photos-mcp.example.com/mcp` |
| `LIBREPHOTOS_MCP_PRINCIPALS_FILE` | Protected subject-to-key JSON file inside the service |
| `LIBREPHOTOS_MCP_ENABLE_WRITES` | `false` by default; `true` registers write tools |

Point `LIBREPHOTOS_URL` to the app or proxy that serves media bytes. A bare
backend can return only media-authorization headers.

Run `librephotos-mcp --transport streamable-http`. The local default is
`127.0.0.1:8000`. Put a trusted HTTPS reverse proxy before a shared service.
The proxy must preserve the public Host header. Host and Origin checks use the
configured public resource URL. HTTP sessions are stateless. Every request is
authenticated. A separate OAuth deployment is required for shared HTTP.

### Docker

Use `deploy/compose/docker-compose.mcp.yml`. Set the variables above.
Set `LIBREPHOTOS_MCP_PRINCIPALS_PATH` to the absolute host credentials-file path.
The container runs as UID 10001. The file must be readable by that UID and must
have no group or other permissions. Set `LIBREPHOTOS_NETWORK` to the existing
LibrePhotos Docker network name.

```bash
docker compose -f deploy/compose/docker-compose.mcp.yml build
docker compose -f deploy/compose/docker-compose.mcp.yml up -d
```

The compose file exposes port 8000 only on the Docker network. Connect the
HTTPS reverse proxy to that network. It mounts only the credentials file.
Rebuild the image after source changes. Dependency installation uses a separate
Docker layer. No PostgreSQL or NAS mount is required.

## Tools and limits

| Tool | Behavior |
| --- | --- |
| `search_photos` | Search captions, tags, OCR, and metadata. Supports semantic mode, dates, people, album, camera, rating, and file-type filters. |
| `get_photo` | Read bounded metadata, captions, people, and album references with sharing redaction. |
| `get_photo_preview` | Return authenticated image content for vision clients. |
| `find_similar_photos` | Use the active embedding index. Preserve relevance order. |
| `list_people` | Page through the caller's people. |
| `list_albums` | Page through the caller's user albums. |
| `get_album` | Read an owned or shared user album and one page of vouched photos. |
| `check_file_exists` | Check a 32-character MD5 digest in the caller's library. SHA-256 is not supported. |
| `check_files_exist` | [Check up to 100 MD5 digests in one call](#batch-file-lookup). |
| `get_job_status` | Read an owned job by its job UUID. Return status, progress, and redacted error summaries. |

Lists return `count`, `page`, `page_size`, `num_pages`, and `results`.
Request the next page while `page < num_pages`. The default limit is 25.
The maximum limit is 100. Photo results include stable UUID identifiers. Summary results include `type`: `image`, `video`, or `motion_photo`. Video previews use a still thumbnail. Image hashes are separate legacy
identifiers. They can contain the content MD5 and an owner-id suffix.
Do not treat an image hash as a bare content digest.
Search filters inspect the caller's own library. Album reads can include shared
photos under the album and library sharing rules.

An explicitly requested semantic search fails if inference or its index is
unavailable. It does not silently return metadata-only results.
Semantic and similarity retrieval use at most 1000 candidates. Metadata search
can page through all matches. One photo detail returns at most 100 people and
100 album references. Captions are limited to 16384 characters.
JSON bodies and previews are limited to 2 MiB. Previews support JPEG, PNG, and
WebP. Redirects and previews from other origins are refused. Filesystem paths
are excluded. Job error counts and generic failure summaries are returned. Full job diagnostics
remain on the LibrePhotos Jobs page.

Photo text is untrusted data. Clients must not treat captions or names as
instructions or authorization to call write tools.

## Batch file lookup

<Since version="1.6.0" />

Call `check_files_exist` with `md5s`, an array of 1 to 100 MD5 digests.
Use 32 hexadecimal characters per digest. Uppercase input is accepted.
The response contains one result per digest in input order, including repeats.
Each result contains `md5`, `exists`, and `photo_id`.
The response returns a lowercase digest and a null photo ID when no match exists.
The tool requires `photos:read`. The lookup checks the caller's own catalog.

The result matches `check_file_exists` for the same digest.
This tool checks catalog records. It does not verify the bytes on disk.
The MCP adapter and the LibrePhotos REST API must both support batch lookup.

## Optional writes

Set `LIBREPHOTOS_MCP_ENABLE_WRITES=true` to register these tools:

| Tool | Required API-key permission |
| --- | --- |
| `update_photo_metadata` | `metadata:write` |
| `update_album_photos` | `albums:write`; removal also uses `photos:read` to resolve UUIDs |
| `start_scan` | `jobs:submit` |
| `generate_captions` | `jobs:submit` |

The adapter uses existing metadata history, album permissions, and job queues.
Metadata changes follow the account's writeback settings. They can modify
sidecars or original files. Album changes can expose photos through existing
album shares. Scan and caption tools return a job UUID immediately.
Removing a photo from an album deletes its comments and likes in that album.
The operation does not delete the original photo file.
Use `get_job_status` to track completion. Tool annotations do not replace
LibrePhotos permission checks.

## Troubleshooting

- HTTP 401: verify issuer, audience, expiry, and subject mapping.
- HTTP 403: request the `librephotos:mcp` scope.
- LibrePhotos permission refused: verify the mapped key, its expiry, and its scopes.
- Missing object: verify ownership or a current share. Other users' private objects remain hidden.
- Response too large: reduce the requested page size. For a large preview, use a smaller generated thumbnail.
- Invalid configuration: verify URLs and credentials-file permissions. Credentials are never echoed in errors.
- Unavailable semantic results: verify the active embedding index and complete its rebuild when required.

Protocol references: [MCP authorization](https://modelcontextprotocol.io/specification/latest/basic/authorization)
and the [official Python SDK](https://github.com/modelcontextprotocol/python-sdk).

## Persistent HTTP tokens

Set `LIBREPHOTOS_MCP_AUTH_MODE=token` to use provisioned bearer tokens without
an OAuth provider. Clients must support an explicit `Authorization` header.
This mode does not provide OAuth discovery or browser sign-in.
Use HTTPS outside a trusted LAN.

Keep the subject-to-API-key map in `LIBREPHOTOS_MCP_PRINCIPALS_FILE`.
Set `LIBREPHOTOS_MCP_TOKENS_FILE` to an owner-only JSON file:

```json
{
  "REPLACE_WITH_SHA256_HEX_DIGEST": "issuer-subject-for-alice"
}
```

Generate each client token as `lpmcp_` plus 32 random bytes encoded with
URL-safe Base64. Store only its SHA-256 hexadecimal digest in this file.
The subject must exist in the API-key map. The MCP token and API key are separate.
Tokens do not expire automatically. Remove a verifier to revoke that token.
The service reads this file for every authenticated request.
Mount the credentials directory so atomic file replacements are visible.
Keep the directory mode `0700` and files mode `0600`, readable by UID 10001.
Revoking the mapped LibrePhotos key also stops access to the library.

Set `LIBREPHOTOS_MCP_RESOURCE_URL` to the exact MCP URL.
The issuer and JWKS settings are unused in token mode.
For example, connect to `http://192.168.86.16:19851/mcp` on the trusted LAN
with `Authorization: Bearer <persistent MCP token>`.
The docker-srv deployment uses `deploy/docker-srv/mcp.compose.yaml`.
Read tools remain the default. API-key capabilities still authorize every call.
