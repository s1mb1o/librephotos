"""Persistent-token HTTP transport with the SDK's authentication middleware."""

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from librephotos_mcp.auth import MCP_SCOPE, PersistentTokenVerifier
from librephotos_mcp.config import Config


class RequireTokenMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.require = RequireAuthMiddleware(app, [MCP_SCOPE])

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            await self.require(scope, receive, send)
        else:
            await self.app(scope, receive, send)


def token_http_app(
    server: MCPServer, config: Config, security: TransportSecuritySettings
) -> Starlette:
    if config.transport != "streamable-http" or config.auth_mode != "token":
        raise ValueError("Persistent-token HTTP requires token authentication.")
    app = server.streamable_http_app(
        stateless_http=True, json_response=True, transport_security=security
    )
    app.add_middleware(RequireTokenMiddleware)
    app.add_middleware(AuthContextMiddleware)
    app.add_middleware(
        AuthenticationMiddleware, backend=BearerAuthBackend(PersistentTokenVerifier(config))
    )
    return app
