"""Validate real authenticated Django responses, not hand-written approximations."""

import base64
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from mcp import Client

from librephotos_mcp.client import LibrePhotosClient
from librephotos_mcp.config import Config
from librephotos_mcp.models import (
    Album,
    AlbumPhotos,
    FileExists,
    JobStarted,
    Page,
    Person,
    PhotoDetail,
    PhotoSummary,
    UpstreamJob,
)
from librephotos_mcp.server import create_server

FIXTURES = Path(__file__).parent / "fixtures" / "backend.json"


class BackendContractsTest(unittest.IsolatedAsyncioTestCase):
    def test_real_responses_match_adapter_models(self) -> None:
        payload = json.loads(FIXTURES.read_text())
        for name, model in [
            ("search", Page[PhotoSummary]),
            ("video_search", Page[PhotoSummary]),
            ("video_photo", PhotoDetail),
            ("photo", PhotoDetail),
            ("shared_photo_hidden", PhotoDetail),
            ("shared_photo_caption", PhotoDetail),
            ("member_photo", PhotoDetail),
            ("member_album", AlbumPhotos),
            ("person_photo", PhotoDetail),
            ("contributor_photo", PhotoDetail),
            ("contributor_album", AlbumPhotos),
            ("people", Page[Person]),
            ("albums", Page[Album]),
            ("album", AlbumPhotos),
            ("job", UpstreamJob),
            ("exists", FileExists),
            ("caption_job", JobStarted),
            ("scan_job", JobStarted),
        ]:
            with self.subTest(name=name):
                model.model_validate(payload[name])
        self.assertEqual(payload["photo"]["caption"], "A blue square")
        self.assertIn(payload["shared_photo_hidden"]["caption"], (None, ""))
        self.assertEqual(payload["metadata_write"], 200)
        self.assertEqual(payload["album_add"], 200)
        self.assertEqual(payload["album_remove"], 200)
        self.assertIn(payload["foreign_album_add"], (400, 403, 404))
        self.assertEqual(payload["video_search"]["results"][0]["type"], "video")
        self.assertTrue(payload["exists"]["exists"])

    async def test_tools_consume_real_backend_responses_and_preview_bytes(self) -> None:
        payload = json.loads(FIXTURES.read_text())
        photo_id = payload["photo"]["id"]
        album_id = payload["album"]["album"]["id"]
        job_id = payload["job"]["job_id"]

        def backend(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.startswith("/media/"):
                return httpx.Response(
                    200,
                    content=base64.b64decode(payload["preview"]["data"]),
                    headers={"content-type": payload["preview"]["mime_type"]},
                )
            name = "search"
            if path.endswith(f"/photos/{photo_id}/"):
                name = "photo"
            elif path == "/api/persons/":
                name = "people"
            elif path == "/api/albums/user/list/":
                name = "albums"
            elif path.startswith("/api/integrations/albums/"):
                name = "album"
            elif path.startswith("/api/integrations/jobs/"):
                name = "job"
            elif path.startswith("/api/exists/"):
                name = "exists"
            return httpx.Response(200, json=payload[name])

        def factory(base_url: str, api_key: str) -> LibrePhotosClient:
            return LibrePhotosClient(base_url, api_key, httpx.MockTransport(backend))

        with patch("librephotos_mcp.server.LibrePhotosClient", side_effect=factory):
            async with Client(
                create_server(Config("http://backend.test", "lp_test-fixture"))
            ) as client:
                for tool, arguments in [
                    ("search_photos", {}),
                    ("get_photo", {"photo_id": photo_id}),
                    ("list_people", {}),
                    ("list_albums", {}),
                    ("get_album", {"album_id": album_id}),
                    ("find_similar_photos", {"photo_id": photo_id}),
                    ("check_file_exists", {"md5": payload["content_md5"]}),
                    ("get_job_status", {"job_id": job_id}),
                ]:
                    result = await client.call_tool(tool, arguments)
                    self.assertFalse(result.is_error, (tool, result))
                    self.assertNotIn("/volume1/", json.dumps(result.model_dump()))
                    self.assertNotIn("Family Photos", json.dumps(result.model_dump()))
                result = await client.call_tool("get_photo_preview", {"photo_id": photo_id})
                self.assertFalse(result.is_error)
                self.assertEqual(result.content[0].type, "image")
                self.assertEqual(
                    base64.b64decode(result.content[0].data),
                    base64.b64decode(payload["preview"]["data"]),
                )

    async def test_video_type_still_preview_and_job_responses(self) -> None:
        payload = json.loads(FIXTURES.read_text())
        video = payload["video_photo"]
        seen: list[str] = []

        def backend(request: httpx.Request) -> httpx.Response:
            seen.append(request.url.path)
            if request.url.path.startswith("/media/"):
                return httpx.Response(
                    200,
                    content=base64.b64decode(payload["video_preview"]["data"]),
                    headers={"content-type": "image/webp"},
                )
            if request.url.path.startswith("/api/integrations/photos/"):
                return httpx.Response(200, json=video)
            return httpx.Response(200, json=payload["video_search"])

        def factory(base_url: str, api_key: str) -> LibrePhotosClient:
            return LibrePhotosClient(base_url, api_key, httpx.MockTransport(backend))

        with patch("librephotos_mcp.server.LibrePhotosClient", side_effect=factory):
            async with Client(create_server(Config("http://backend.test", "lp_fixture"))) as client:
                result = await client.call_tool(
                    "search_photos", {"filters": {"file_type": "video"}}
                )
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content["results"][0]["type"], "video")
                result = await client.call_tool("get_photo_preview", {"photo_id": video["id"]})
                self.assertFalse(result.is_error)
                self.assertEqual(seen[-1], f"/media/thumbnails_big/{video['image_hash']}")
        for name in ("scan_job", "caption_job"):
            async with LibrePhotosClient(
                "http://backend.test",
                "lp_fixture",
                httpx.MockTransport(lambda request: httpx.Response(200, json=payload[name])),
            ) as api:
                result = await api.job("/api/synthetic-job/")
                self.assertEqual(result["job_id"], payload[name]["job_id"])
