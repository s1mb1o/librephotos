"""Draft provider tests never save settings, read library photos, or rebuild indexes."""

import json
from unittest.mock import Mock, patch

import requests
from constance import config
from constance.test import override_config
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import (
    EmbeddingSpace,
    LongRunningJob,
    PhotoEmbedding,
    RemoteModelConfig,
    SemanticIndex,
)
from api.runtime.model_settings import save_remote_config
from api.search.profiles import EmbeddingProfile, activate_profile, active_profile
from api.search.semantic import SIGLIP2
from api.tests.ml_services.test_remote_captioning import reply
from api.tests.utils import create_test_user

URL = "/api/sitesettings/test-model/"


@override_config(CAPTIONING_MODEL="lfm2_vl_450m", EMBEDDING_MODEL="openclip_vitb32")
class RemoteModelCheckTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.admin = create_test_user(is_admin=True)
        self.client.force_authenticate(self.admin)
        for kind in ("captioning", "embeddings"):
            save_remote_config(
                kind,
                {
                    "url": "http://saved.example/v1",
                    "model_name": "saved-model",
                    "token": "saved-private-token",
                },
            )

        self.profile = EmbeddingProfile(
            SIGLIP2, "http://active.example/v1", "active-model", token="active-token"
        )
        activate_profile(self.admin, self.profile)

    def assert_unchanged(self) -> None:
        self.assertEqual(config.CAPTIONING_MODEL, "lfm2_vl_450m")
        self.assertEqual(config.EMBEDDING_MODEL, "openclip_vitb32")
        for saved in RemoteModelConfig.objects.all():
            self.assertEqual(saved.url, "http://saved.example/v1")
            self.assertEqual(saved.model_name, "saved-model")
            self.assertEqual(saved.token, "saved-private-token")
            self.assertFalse(saved.disable_thinking)
            self.assertEqual(saved.max_num_patches, 256)
        self.assertEqual(EmbeddingSpace.objects.count(), 1)
        self.assertEqual(SemanticIndex.objects.count(), 1)
        self.assertEqual(active_profile(self.admin).key, self.profile.key)
        self.assertEqual(active_profile(self.admin).token, self.profile.token)
        for model in (PhotoEmbedding, LongRunningJob):
            self.assertFalse(model.objects.exists())

    @patch("api.runtime.remote_inference.requests.post")
    def test_unsaved_caption_settings_and_image_are_tested_without_saving(
        self, post: Mock
    ) -> None:
        post.return_value = reply(
            {"choices": [{"message": {"content": "A red square and a blue circle."}}]}
        )
        response = self.client.post(
            URL,
            {
                "kind": "captioning",
                "settings": {
                    "url": "http://draft.example/v1",
                    "model_name": "draft-model",
                    "token": "draft-token",
                    "disable_thinking": True,
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"kind": "captioning", "dimension": None})
        self.assertEqual(
            post.call_args.args[0], "http://draft.example/v1/chat/completions"
        )
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"], "Bearer draft-token"
        )
        body = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(body["model"], "draft-model")
        self.assertFalse(body["chat_template_kwargs"]["enable_thinking"])
        self.assertTrue(
            body["messages"][0]["content"][1]["image_url"]["url"].startswith(
                "data:image/jpeg;base64,"
            )
        )
        self.assertNotIn("draft-token", str(response.data))
        self.assert_unchanged()

    @patch("api.runtime.remote_inference.requests.post")
    def test_blank_token_reuses_saved_token_and_clear_token_is_honored(
        self, post: Mock
    ) -> None:
        post.return_value = reply(
            {"choices": [{"message": {"content": "Test caption."}}]}
        )
        for settings, authenticated in (
            ({"token": ""}, True),
            ({"token": "draft-token", "clear_token": True}, False),
        ):
            response = self.client.post(
                URL, {"kind": "captioning", "settings": settings}, format="json"
            )
            self.assertEqual(response.status_code, 200)
            headers = post.call_args.kwargs["headers"]
            self.assertEqual("Authorization" in headers, authenticated)
            if authenticated:
                self.assertEqual(headers["Authorization"], "Bearer saved-private-token")
        self.assert_unchanged()

    @patch("api.runtime.remote_inference.requests.post")
    def test_embedding_test_checks_both_image_and_text_with_draft_patch_budget(
        self, post: Mock
    ) -> None:
        post.return_value = reply(
            {
                "model": "draft-siglip",
                "data": [{"index": 0, "embedding": [1.0] + [0.0] * 1151}],
            }
        )
        response = self.client.post(
            URL,
            {
                "kind": "embeddings",
                "settings": {"model_name": "draft-siglip", "max_num_patches": 512},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"kind": "embeddings", "dimension": 1152})
        self.assertEqual(post.call_count, 2)
        image, text = [json.loads(call.kwargs["data"]) for call in post.call_args_list]
        self.assertTrue(image["input"][0].startswith("data:image/jpeg;base64,"))
        self.assertEqual(text["input"], ["A red square and a blue circle on white."])
        self.assertEqual(image["max_num_patches"], 512)
        self.assertEqual(text["max_num_patches"], 512)
        self.assert_unchanged()

    @patch("api.runtime.remote_inference.requests.post")
    def test_provider_errors_do_not_disclose_secrets_or_change_settings(
        self, post: Mock
    ) -> None:
        for upstream in (
            reply(
                {"error": "saved-private-token draft-token private upstream text"}, 401
            ),
            reply({"choices": []}),
            reply({"model": "saved-model", "data": [{"index": 0, "embedding": [1.0]}]}),
        ):
            post.return_value = upstream
            kind = "embeddings" if "data" in upstream.json() else "captioning"
            response = self.client.post(
                URL, {"kind": kind, "settings": {}}, format="json"
            )
            self.assertEqual(response.status_code, 400)
            for value in (
                "saved-private-token",
                "draft-token",
                "private upstream text",
            ):
                self.assertNotIn(value, str(response.data))
        self.assert_unchanged()

    @patch("api.runtime.remote_inference.requests.post")
    def test_timeouts_and_invalid_json_are_actionable(self, post: Mock) -> None:
        post.side_effect = requests.Timeout("private endpoint saved-private-token")
        response = self.client.post(
            URL, {"kind": "captioning", "settings": {}}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("timed out", str(response.data))
        self.assertNotIn("saved-private-token", str(response.data))
        post.side_effect = None
        post.return_value = reply("not an object")
        response = self.client.post(
            URL, {"kind": "captioning", "settings": {}}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assert_unchanged()

    @patch("api.runtime.remote_inference.requests.post")
    def test_invalid_drafts_make_no_provider_request(self, post: Mock) -> None:
        for data in (
            {"kind": "unknown", "settings": {}},
            {"kind": "captioning", "settings": {"url": "file:///private"}},
            {"kind": "captioning", "settings": {"url": "", "model_name": ""}},
            {"kind": "embeddings", "settings": {"max_num_patches": 0}},
        ):
            response = self.client.post(URL, data, format="json")
            self.assertEqual(response.status_code, 400)
        post.assert_not_called()
        self.assert_unchanged()

    @patch("api.runtime.remote_inference.requests.post")
    def test_only_administrators_can_test_providers(self, post: Mock) -> None:
        for user in (None, create_test_user()):
            self.client.force_authenticate(user)
            response = self.client.post(
                URL, {"kind": "captioning", "settings": {}}, format="json"
            )
            self.assertIn(response.status_code, (401, 403))
        post.assert_not_called()
        self.assert_unchanged()
