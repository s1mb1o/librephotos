"""OAuth resource-server verification. MCP tokens never authenticate REST calls."""

import asyncio
import time

import jwt
from mcp.server.auth.provider import AccessToken

from librephotos_mcp.config import Config

MCP_SCOPE = "librephotos:mcp"


class OAuthVerifier:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.jwks = jwt.PyJWKClient(config.jwks_url, timeout=10)
        self._keys: dict[str | None, jwt.PyJWK] = {}
        self._keys_at = float("-inf")
        self._last_attempt = float("-inf")
        self._refresh_lock = asyncio.Lock()

    async def _signing_key(self, token: str) -> jwt.PyJWK | None:
        header = jwt.get_unverified_header(token)
        kid: object = header.get("kid")
        if header.get("alg") not in {"RS256", "ES256"}:
            return None
        if not isinstance(kid, str) or not kid or len(kid) > 256:
            return None
        cached = self._keys.get(kid)
        if cached is not None and time.monotonic() - self._keys_at < 300:
            return cached
        async with self._refresh_lock:
            now = time.monotonic()
            cached = self._keys.get(kid)
            if cached is not None and now - self._keys_at < 300:
                return cached
            if now - self._last_attempt < 60:
                return None
            self._last_attempt = now
            keys = await asyncio.to_thread(self.jwks.get_signing_keys, refresh=True)
            self._keys = {key.key_id: key for key in keys}
            self._keys_at = now
            return self._keys.get(kid)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            key = await self._signing_key(token)
            if key is None:
                return None
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256", "ES256"],
                audience=self.config.resource_url,
                issuer=self.config.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
            subject = claims.get("sub")
            scope = claims.get("scope", "")
            if (
                not isinstance(subject, str)
                or subject not in self.config.principals
                or not isinstance(scope, str)
            ):
                return None
            return AccessToken(
                token=token,
                client_id=str(claims.get("client_id", claims.get("azp", subject))),
                subject=subject,
                scopes=scope.split(),
                expires_at=int(claims["exp"]),
                resource=self.config.resource_url,
            )
        except (jwt.PyJWTError, ValueError, TypeError, OSError):
            return None
