"""Protocol, identity, bounds and failure tests without production services."""

import asyncio
import base64
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import httpx2
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp import Client
from mcp.client.client import streamable_http_client
from mcp.client.stdio import StdioServerParameters
from mcp.server.transport_security import TransportSecuritySettings

from librephotos_mcp.auth import MCP_SCOPE, OAuthVerifier
from librephotos_mcp.client import LibrePhotosClient, LibrePhotosError
from librephotos_mcp.config import Config, protected_file
from librephotos_mcp.server import create_server

PHOTO = "11111111-1111-4111-8111-111111111111"
HASH = "a" * 32
KEY = "lp_fixture-only"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a/1sAAAAASUVORK5CYII="
)


def page() -> dict[str, object]:
    return {
        "count": 1,
        "page": 1,
        "page_size": 25,
        "num_pages": 1,
        "next": None,
        "previous": None,
        "results": [{"id": PHOTO, "image_hash": HASH, "date": "", "type": "image"}],
    }


class AdapterTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.requests: list[httpx.Request] = []

        def backend(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            path = request.url.path
            if path.endswith(f"/photos/{PHOTO}/"):
                return httpx.Response(
                    200,
                    json={
                        "id": PHOTO,
                        "image_hash": HASH,
                        "people": [],
                        "album_refs": [],
                        "caption": "A test photo",
                        "square_thumbnail_url": f"/media/square_thumbnails/{HASH}",
                        "image_path": "/volume1/private/original.jpg",
                    },
                )
            if path == "/api/persons/":
                return httpx.Response(200, json={**page(), "results": [{"id": 1, "name": "Alice"}]})
            if path == "/api/albums/user/list/":
                return httpx.Response(200, json={**page(), "results": [{"id": 1, "title": "Test"}]})
            if path.startswith("/api/integrations/albums/"):
                return httpx.Response(200, json={**page(), "album": {"id": 1, "title": "Test"}})
            if path.startswith("/api/integrations/jobs/"):
                return httpx.Response(
                    200,
                    json={
                        "job_id": PHOTO,
                        "finished": True,
                        "failed": True,
                        "cancelled": False,
                        "progress_current": 1,
                        "progress_target": 2,
                        "progress_step": "/volume1/private",
                        "result": {"errors": ["Cannot read /volume1/private"]},
                    },
                )
            if path in {"/api/scanphotos/", "/api/generate-captions/"}:
                return httpx.Response(200, json={"job_id": PHOTO})
            if path.startswith("/media/"):
                return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
            if path.startswith("/api/exists/"):
                return httpx.Response(200, json={"exists": True, "photo_id": PHOTO})
            return httpx.Response(200, json=page())

        self.backend = backend

        def factory(base_url: str, api_key: str) -> LibrePhotosClient:
            return LibrePhotosClient(base_url, api_key, httpx.MockTransport(self.backend))

        self.factory = patch("librephotos_mcp.server.LibrePhotosClient", side_effect=factory)
        self.factory.start()
        self.server = create_server(Config("http://backend.test", KEY))

    async def asyncTearDown(self) -> None:
        self.factory.stop()

    async def test_discovery_and_bounded_search_via_official_client(self) -> None:
        async with Client(self.server) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            self.assertEqual(len(names), 9)
            self.assertNotIn("start_scan", names)
            result = await client.call_tool(
                "search_photos",
                {
                    "query": "beach",
                    "limit": 12,
                    "page": 2,
                    "semantic": True,
                    "filters": {"person": [1, 2], "taken_after": "2026-01-01"},
                },
            )
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["results"][0]["id"], PHOTO)
        request = self.requests[-1]
        self.assertEqual(request.headers["Authorization"], f"Api-Key {KEY}")
        self.assertEqual(request.url.params["page_size"], "12")
        self.assertEqual(request.url.params.get_list("person"), ["1", "2"])

    async def test_invalid_ids_and_limits_do_not_call_backend(self) -> None:
        async with Client(self.server) as client:
            for tool, args in [
                ("get_photo", {"photo_id": "../../etc/passwd"}),
                ("search_photos", {"limit": 101}),
                ("check_file_exists", {"md5": "a" * 64}),
            ]:
                result = await client.call_tool(tool, args)
                self.assertTrue(result.is_error)
        self.assertEqual(self.requests, [])

    async def test_photo_paths_are_excluded_and_preview_is_image_content(self) -> None:
        async with Client(self.server) as client:
            detail = await client.call_tool("get_photo", {"photo_id": PHOTO})
            self.assertNotIn("/volume1/", json.dumps(detail.model_dump()))
            preview = await client.call_tool("get_photo_preview", {"photo_id": PHOTO})
            self.assertFalse(preview.is_error)
            self.assertEqual(preview.content[0].type, "image")
            self.assertEqual(base64.b64decode(preview.content[0].data), PNG)
        self.assertTrue(
            all(request.headers["Authorization"] == f"Api-Key {KEY}" for request in self.requests)
        )

    async def test_remaining_read_tools_have_usable_responses(self) -> None:
        async with Client(self.server) as client:
            for tool, arguments in [
                ("list_people", {}),
                ("list_albums", {}),
                ("get_album", {"album_id": 1}),
                ("find_similar_photos", {"photo_id": PHOTO}),
                ("get_job_status", {"job_id": PHOTO}),
            ]:
                result = await client.call_tool(tool, arguments)
                self.assertFalse(result.is_error, result)
                self.assertNotIn("/volume1/", json.dumps(result.model_dump()))

    async def test_write_tools_map_album_removal_and_return_jobs_promptly(self) -> None:
        server = create_server(Config("http://backend.test", KEY, enable_writes=True))
        async with Client(server) as client:
            result = await client.call_tool(
                "update_album_photos", {"album_id": 1, "remove_photo_ids": [PHOTO]}
            )
            self.assertFalse(result.is_error, result)
            self.assertEqual(json.loads(self.requests[-1].content), {"removedPhotos": [HASH]})
            for name in ["start_scan", "generate_captions"]:
                result = await client.call_tool(name, {})
                self.assertFalse(result.is_error, result)
                self.assertEqual(result.structured_content["job_id"], PHOTO)

    async def test_md5_lookup(self) -> None:
        async with Client(self.server) as client:
            result = await client.call_tool("check_file_exists", {"md5": HASH.upper()})
            self.assertEqual(result.structured_content, {"exists": True, "photo_id": PHOTO})
        self.assertEqual(self.requests[-1].url.path, f"/api/exists/{HASH}/")

    async def test_writes_are_opt_in(self) -> None:
        server = create_server(Config("http://backend.test", KEY, enable_writes=True))
        async with Client(server) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            self.assertIn("start_scan", names)
            self.assertIn("update_photo_metadata", names)
            result = await client.call_tool(
                "update_photo_metadata", {"photo_id": PHOTO, "caption": "Updated"}
            )
            self.assertFalse(result.is_error)
        self.assertEqual(self.requests[-1].method, "PATCH")
        self.assertEqual(json.loads(self.requests[-1].content), {"caption": "Updated"})

    async def test_upstream_errors_do_not_expose_secrets(self) -> None:
        for status in [401, 403, 404, 500, 302]:

            def error(request: httpx.Request) -> httpx.Response:
                return httpx.Response(
                    status,
                    text="secret-token /volume1/private",
                    headers={"Location": "http://evil.test/"},
                )

            self.backend = error
            async with Client(self.server) as client:
                result = await client.call_tool("get_photo", {"photo_id": PHOTO})
                self.assertTrue(result.is_error)
                output = json.dumps(result.model_dump())
                self.assertNotIn("secret-token", output)
                self.assertNotIn("/volume1/", output)

    async def test_malformed_and_unbounded_json_is_refused(self) -> None:
        for payload in [
            b"not json",
            b"x" * (2 * 1024 * 1024 + 1),
            json.dumps({**page(), "results": page()["results"] * 101}).encode(),
        ]:
            self.backend = lambda request: httpx.Response(200, content=payload)
            async with Client(self.server) as client:
                result = await client.call_tool("search_photos", {})
                self.assertTrue(result.is_error)

    async def test_timeout_is_redacted(self) -> None:
        def timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("secret-token /volume1/private")

        self.backend = timeout
        async with Client(self.server) as client:
            result = await client.call_tool("search_photos", {})
            self.assertTrue(result.is_error)
            self.assertNotIn("secret-token", json.dumps(result.model_dump()))

    async def test_write_outcomes_do_not_encourage_duplicate_submissions(self) -> None:
        def timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("private backend detail")

        async with LibrePhotosClient(
            "http://backend.test", KEY, httpx.MockTransport(timeout)
        ) as api:
            with self.assertRaisesRegex(LibrePhotosError, "outcome is unknown"):
                await api.job("/api/scanphotos/")
        for body in [b"invalid json", b'{"job_id":"private-path"}', b"x" * 2097153]:
            async with LibrePhotosClient(
                "http://backend.test",
                KEY,
                httpx.MockTransport(lambda request: httpx.Response(200, content=body)),
            ) as api:
                with self.assertRaisesRegex(LibrePhotosError, "Check Jobs"):
                    await api.job("/api/scanphotos/")

    async def test_proxy_write_failures_have_unknown_outcomes(self) -> None:
        for status in (500, 502, 504):
            async with LibrePhotosClient(
                "http://backend.test",
                KEY,
                httpx.MockTransport(lambda request: httpx.Response(status, text="private detail")),
            ) as api:
                with self.assertRaisesRegex(LibrePhotosError, "outcome is unknown"):
                    await api.job("/api/scanphotos/")

        async with LibrePhotosClient(
            "http://backend.test",
            KEY,
            httpx.MockTransport(
                lambda request: httpx.Response(
                    200, headers={"content-encoding": "gzip"}, stream=httpx.ByteStream(b"unused")
                )
            ),
        ) as api:
            with self.assertRaisesRegex(LibrePhotosError, "outcome is unknown"):
                await api.job("/api/scanphotos/")

    async def test_metadata_patch_ignores_unused_response_body(self) -> None:
        async with LibrePhotosClient(
            "http://backend.test",
            KEY,
            httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=b"x" * 2097153,
                )
            ),
        ) as api:
            await api.change("/api/photos/fixture/", {"caption": "Changed"})

    async def test_preview_rejects_other_origins_paths_mime_and_size(self) -> None:
        async with LibrePhotosClient(
            "http://backend.test", KEY, httpx.MockTransport(self.backend)
        ) as api:
            for url in [
                "http://evil.test/media/image",
                "//evil.test/media/image",
                "/api/auth/keys/",
                "/media/%2e%2e/secret",
                "/media/%252e%252e/secret",
                "/media/image%3Fprivate",
                "/media/image%23private",
                "/media/image?api_key=secret",
            ]:
                with self.assertRaises(LibrePhotosError):
                    await api.preview(url)
        for content, mime in [
            (b"<svg/>", "image/svg+xml"),
            (b"x" * (2 * 1024 * 1024 + 1), "image/png"),
        ]:
            async with LibrePhotosClient(
                "http://backend.test",
                KEY,
                httpx.MockTransport(
                    lambda request: httpx.Response(
                        200, content=content, headers={"content-type": mime}
                    )
                ),
            ) as api:
                with self.assertRaises(LibrePhotosError):
                    await api.preview("/media/image")


class OAuthHTTPTest(unittest.IsolatedAsyncioTestCase):
    async def test_authorized_http_uses_separate_per_subject_keys(self) -> None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        config = Config(
            "http://backend.test",
            transport="streamable-http",
            issuer="https://issuer.test",
            jwks_url="https://issuer.test/jwks",
            resource_url="https://mcp.test/mcp",
            principals={"alice": "lp_alice", "bob": "lp_bob"},
        )
        seen: list[str] = []

        def backend(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers["Authorization"])
            return httpx.Response(200, json=page())

        def factory(base_url: str, api_key: str) -> LibrePhotosClient:
            return LibrePhotosClient(base_url, api_key, httpx.MockTransport(backend))

        with (
            patch(
                "librephotos_mcp.auth.jwt.PyJWKClient.get_signing_keys",
                return_value=[SimpleNamespace(key=key.public_key(), key_id="test")],
            ),
            patch("librephotos_mcp.server.LibrePhotosClient", side_effect=factory),
        ):
            server = create_server(config)
            app = server.streamable_http_app(
                stateless_http=True,
                json_response=True,
                transport_security=TransportSecuritySettings(
                    allowed_hosts=["mcp.test"], allowed_origins=["https://mcp.test"]
                ),
            )
            async with app.router.lifespan_context(app):
                for subject in ["alice", "bob", "alice"]:
                    token = jwt.encode(
                        {
                            "sub": subject,
                            "iss": config.issuer,
                            "aud": config.resource_url,
                            "exp": int(time.time()) + 60,
                            "scope": MCP_SCOPE,
                        },
                        key,
                        algorithm="RS256",
                        headers={"kid": "test"},
                    )
                    async with httpx2.AsyncClient(
                        transport=httpx2.ASGITransport(app=app),
                        headers={"Authorization": f"Bearer {token}"},
                    ) as http:
                        async with Client(
                            streamable_http_client("https://mcp.test/mcp", http_client=http)
                        ) as client:
                            result = await client.call_tool("search_photos", {})
                            self.assertFalse(result.is_error)
                async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app)) as http:
                    unauthorized = await http.post("https://mcp.test/mcp", json={})
                    self.assertEqual(unauthorized.status_code, 401)
                    self.assertIn("resource_metadata", unauthorized.headers["www-authenticate"])
                    metadata = await http.get(
                        "https://mcp.test/.well-known/oauth-protected-resource/mcp"
                    )
                    self.assertEqual(metadata.status_code, 200)
                    self.assertEqual(metadata.json()["authorization_servers"], [config.issuer])
                    missing_scope = jwt.encode(
                        {
                            "sub": "alice",
                            "iss": config.issuer,
                            "aud": config.resource_url,
                            "exp": int(time.time()) + 60,
                            "scope": "other",
                        },
                        key,
                        algorithm="RS256",
                        headers={"kid": "test"},
                    )
                    denied = await http.post(
                        "https://mcp.test/mcp",
                        headers={"Authorization": f"Bearer {missing_scope}"},
                        json={},
                    )
                    self.assertEqual(denied.status_code, 403)
                    denied_origin = await http.post(
                        "https://mcp.test/mcp",
                        headers={"Authorization": f"Bearer {token}", "Origin": "https://evil.test"},
                        json={},
                    )
                    self.assertEqual(denied_origin.status_code, 403)
                    denied_host = await http.post(
                        "https://evil.test/mcp",
                        headers={"Authorization": f"Bearer {token}"},
                        json={},
                    )
                    self.assertEqual(denied_host.status_code, 421)
        self.assertEqual(seen, ["Api-Key lp_alice", "Api-Key lp_bob", "Api-Key lp_alice"])

    async def test_expiry_audience_scope_and_unknown_subject_are_refused(self) -> None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        config = Config(
            "http://backend.test",
            transport="streamable-http",
            issuer="https://issuer.test",
            jwks_url="https://issuer.test/jwks",
            resource_url="https://mcp.test/mcp",
            principals={"alice": KEY},
        )
        base = {
            "sub": "alice",
            "iss": config.issuer,
            "aud": config.resource_url,
            "exp": int(time.time()) + 60,
            "scope": MCP_SCOPE,
        }
        verifier = OAuthVerifier(config)
        with patch.object(
            verifier.jwks,
            "get_signing_keys",
            return_value=[SimpleNamespace(key=key.public_key(), key_id="test")],
        ):
            self.assertIsNotNone(
                await verifier.verify_token(
                    jwt.encode(base, key, algorithm="RS256", headers={"kid": "test"})
                )
            )
            for changes in [
                {"exp": 1},
                {"aud": "other"},
                {"iss": "other"},
                {"sub": "unknown"},
            ]:
                self.assertIsNone(
                    await verifier.verify_token(
                        jwt.encode(
                            {**base, **changes}, key, algorithm="RS256", headers={"kid": "test"}
                        )
                    )
                )


class StdioTest(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_protocol_contains_only_mcp_messages(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                body = json.dumps(page()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "librephotos_mcp"],
                env={
                    "LIBREPHOTOS_URL": f"http://127.0.0.1:{http.server_port}",
                    "LIBREPHOTOS_API_KEY": KEY,
                },
            )
            async with Client(params) as client:
                self.assertEqual(len((await client.list_tools()).tools), 9)
                self.assertFalse((await client.call_tool("search_photos", {})).is_error)
        finally:
            await asyncio.to_thread(http.shutdown)
            http.server_close()
            thread.join(timeout=2)


class ConfigurationTest(unittest.TestCase):
    def test_shared_http_requires_oauth_and_protected_credentials(self) -> None:
        with patch.dict(os.environ, {"LIBREPHOTOS_API_KEY": KEY}, clear=True):
            with self.assertRaises(ValueError):
                Config.from_environment("streamable-http")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credential"
            path.write_text(KEY)
            path.chmod(0o600)
            self.assertEqual(protected_file(str(path)), KEY)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                protected_file(str(path))


class AdditionalOAuthTest(unittest.IsolatedAsyncioTestCase):
    async def test_signature_algorithms_and_jwks_refresh_bounds(self) -> None:
        from cryptography.hazmat.primitives.asymmetric import ec

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        config = Config(
            "http://backend.test",
            transport="streamable-http",
            issuer="https://issuer.test",
            jwks_url="https://issuer.test/jwks",
            resource_url="https://mcp.test/mcp",
            principals={"alice": KEY},
        )
        claims = {
            "sub": "alice",
            "iss": config.issuer,
            "aud": config.resource_url,
            "exp": int(time.time()) + 60,
            "scope": MCP_SCOPE,
        }
        verifier = OAuthVerifier(config)
        with patch.object(
            verifier.jwks,
            "get_signing_keys",
            return_value=[SimpleNamespace(key_id="test", key=key.public_key())],
        ) as lookup:
            self.assertIsNotNone(
                await verifier.verify_token(
                    jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})
                )
            )
            self.assertIsNone(
                await verifier.verify_token(
                    jwt.encode(claims, other, algorithm="RS256", headers={"kid": "test"})
                )
            )
            for index in range(20):
                self.assertIsNone(
                    await verifier.verify_token(
                        jwt.encode(
                            claims, key, algorithm="RS256", headers={"kid": f"unknown-{index}"}
                        )
                    )
                )
            self.assertEqual(lookup.call_count, 1)
            self.assertIsNone(
                await verifier.verify_token(
                    jwt.encode(
                        claims, "only-test-secret" * 4, algorithm="HS256", headers={"kid": "test"}
                    )
                )
            )
            self.assertIsNone(
                await verifier.verify_token(
                    jwt.encode(claims, None, algorithm="none", headers={"kid": "test"})
                )
            )
        ec_key = ec.generate_private_key(ec.SECP256R1())
        verifier = OAuthVerifier(config)
        with patch.object(
            verifier.jwks,
            "get_signing_keys",
            return_value=[SimpleNamespace(key_id="ec", key=ec_key.public_key())],
        ):
            self.assertIsNotNone(
                await verifier.verify_token(
                    jwt.encode(claims, ec_key, algorithm="ES256", headers={"kid": "ec"})
                )
            )

    async def test_cli_uses_the_configured_host_and_origin_policy(self) -> None:
        from unittest.mock import Mock

        from librephotos_mcp.__main__ import main

        config = Config(
            "http://backend.test",
            transport="streamable-http",
            issuer="https://issuer.test",
            jwks_url="https://issuer.test/jwks",
            resource_url="https://mcp.test/mcp",
            principals={"alice": KEY},
        )
        server = Mock()
        with (
            patch.object(sys, "argv", ["librephotos-mcp", "--transport", "streamable-http"]),
            patch("librephotos_mcp.__main__.Config.from_environment", return_value=config),
            patch("librephotos_mcp.__main__.create_server", return_value=server),
        ):
            main()
        options = server.run.call_args.kwargs
        self.assertTrue(options["stateless_http"])
        self.assertEqual(options["transport_security"].allowed_hosts, ["mcp.test", "mcp.test:*"])
        self.assertEqual(options["transport_security"].allowed_origins, ["https://mcp.test"])
