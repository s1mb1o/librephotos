---
sidebar_position: 15
---

import Since from '@site/src/components/Since';

# API keys

<Since version="1.6.0" />

Open **Settings → API Keys**. Enter a name. Select permissions.
Leave the expiration empty for a permanent key. Select **Create key**.
Copy the complete key from the dialog. The server shows it only once.
Store it in a password manager or a credentials file with restricted access.

Send the key in a header:

```bash
curl --header "Authorization: Api-Key ${LIBREPHOTOS_API_KEY}" \
  'http://localhost:3000/api/search/?search=beach'
```

Do not put keys in URLs. Do not put keys in source control or logs.
Use HTTPS when requests leave a trusted local network.
JWT sign-in and refresh remain available.

| Permission | Access |
| --- | --- |
| `photos:read` | Photo search, photo details, metadata, people, albums, MD5 lookup, and authorized media |
| `jobs:read` | Job lists and job status |
| `metadata:write` | PATCH photo metadata through the metadata edit service |
| `albums:write` | Create and edit owned user albums |
| `jobs:submit` | Submit incremental scans and caption-generation jobs |

The default permissions are `photos:read` and `jobs:read`.
Every operation also uses the owner's existing permissions and sharing rules.
Unlisted operations are denied. Keys cannot manage API keys, accounts, server
configuration, original-file operations, uploads, or public sharing.
Metadata changes follow the account's metadata writeback settings. They can
modify sidecar or original files when writeback is enabled.

Each key has a non-secret UUID identifier. The list shows its permissions,
creation time, optional expiration time, last-used time, and revocation state.
The server stores a one-way verifier. It does not store the complete key.

Select **Revoke key** to disable one key. Revocation applies to the next
authenticated request. Account deactivation or deletion also invalidates keys.
Create a replacement key before revocation when an integration needs continuous access.

Account credentials are required for `GET/POST /api/auth/keys/` and
`DELETE /api/auth/keys/{id}/`. The POST response contains `key` once.
The DELETE operation retains a revoked metadata record. Authentication results
are not cached. Previously issued JWT credentials do not become API keys.
