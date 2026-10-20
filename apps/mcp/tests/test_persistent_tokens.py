"""Persistent HTTP tokens remain separate from account API keys."""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import httpx2
from mcp import Client
from mcp.client.client import streamable_http_client
from mcp.server.transport_security import TransportSecuritySettings

from librephotos_mcp.auth import PersistentTokenVerifier
from librephotos_mcp.client import LibrePhotosClient
from librephotos_mcp.config import Config
from librephotos_mcp.http import token_http_app
from librephotos_mcp.server import create_server


class PersistentTokensTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.tokens = {name: "lpmcp_" + name * 43 for name in ("a", "b")}
        self.path = self.root / "tokens.json"
        self.write_tokens({name: name for name in self.tokens})
        self.config = Config(
            "http://backend.test",
            transport="streamable-http",
            auth_mode="token",
            tokens_file=str(self.path),
            resource_url="http://mcp.test/mcp",
            principals={"a": "lp_account-a", "b": "lp_account-b"},
        )

    def write_tokens(self, subjects: dict[str, str]) -> None:
        replacement = self.root / "tokens.next"
        replacement.write_text(
            json.dumps(
                {
                    hashlib.sha256(self.tokens[token].encode()).hexdigest(): subject
                    for token, subject in subjects.items()
                }
            )
        )
        replacement.chmod(0o600)
        replacement.replace(self.path)

    async def test_verifier_revocation_rotation_and_fail_closed(self) -> None:
        verifier = PersistentTokenVerifier(self.config)
        self.assertIsNone(await verifier.verify_token("lp_account-a"))
        self.assertIsNone(await verifier.verify_token("lpmcp_" + "x" * 43))
        access = await verifier.verify_token(self.tokens["a"])
        self.assertIsNotNone(access)
        self.assertIsNone(access.expires_at)
        self.write_tokens({"b": "b"})
        self.assertIsNone(await verifier.verify_token(self.tokens["a"]))
        self.assertIsNotNone(await verifier.verify_token(self.tokens["b"]))
        self.path.write_text("invalid-json")
        self.assertIsNone(await verifier.verify_token(self.tokens["b"]))
        self.write_tokens({"a": "unknown"})
        self.assertIsNone(await verifier.verify_token(self.tokens["a"]))
        self.write_tokens({"a": "a"})
        self.path.chmod(0o644)
        self.assertIsNone(await verifier.verify_token(self.tokens["a"]))

    async def test_http_identity_missing_token_and_scope_isolation(self) -> None:
        seen: list[str] = []

        def backend(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers["Authorization"])
            return httpx.Response(
                200,
                json={
                    "count": 0,
                    "page": 1,
                    "page_size": 25,
                    "num_pages": 1,
                    "results": [],
                    "next": None,
                    "previous": None,
                },
            )

        def factory(base_url: str, key: str) -> LibrePhotosClient:
            return LibrePhotosClient(base_url, key, httpx.MockTransport(backend))

        security = TransportSecuritySettings(
            allowed_hosts=["mcp.test"], allowed_origins=["http://mcp.test"]
        )
        with patch("librephotos_mcp.server.LibrePhotosClient", side_effect=factory):
            app = token_http_app(create_server(self.config), self.config, security)
            async with app.router.lifespan_context(app):
                for token in ("", "Bearer lp_account-a", "Basic invalid"):
                    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app)) as http:
                        response = await http.post(
                            "http://mcp.test/mcp", headers={"Authorization": token}, json={}
                        )
                        self.assertEqual(response.status_code, 401)
                for subject in ("a", "b", "a"):
                    async with httpx2.AsyncClient(
                        transport=httpx2.ASGITransport(app=app),
                        headers={"Authorization": f"Bearer {self.tokens[subject]}"},
                    ) as http:
                        async with Client(
                            streamable_http_client("http://mcp.test/mcp", http_client=http)
                        ) as client:
                            self.assertEqual(len((await client.list_tools()).tools), 9)
                            result = await client.call_tool("search_photos", {})
                            self.assertFalse(result.is_error)
                self.write_tokens({"b": "b"})
                async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app)) as http:
                    response = await http.post(
                        "http://mcp.test/mcp",
                        headers={"Authorization": f"Bearer {self.tokens['a']}"},
                        json={},
                    )
                    self.assertEqual(response.status_code, 401)
        self.assertEqual(
            seen, ["Api-Key lp_account-a", "Api-Key lp_account-b", "Api-Key lp_account-a"]
        )
        self.assertTrue(all("lpmcp_" not in header for header in seen))

    async def test_configuration_requires_protected_verifiers_and_known_subjects(self) -> None:
        principals = self.root / "principals.json"
        principals.write_text(json.dumps(self.config.principals))
        principals.chmod(0o600)
        env = {
            "LIBREPHOTOS_MCP_AUTH_MODE": "token",
            "LIBREPHOTOS_MCP_RESOURCE_URL": self.config.resource_url,
            "LIBREPHOTOS_MCP_TOKENS_FILE": str(self.path),
            "LIBREPHOTOS_MCP_PRINCIPALS_FILE": str(principals),
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_environment("streamable-http")
            self.assertEqual(config.auth_mode, "token")
            self.assertEqual(config.issuer, "")
            self.path.unlink()
            with self.assertRaises(OSError):
                Config.from_environment("streamable-http")
