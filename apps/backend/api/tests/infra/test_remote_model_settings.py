"""Only administrators can edit provider settings. Tokens never leave the server."""

from unittest.mock import patch

from constance.test import override_config
from django.db import connection
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import RemoteModelConfig
from api.runtime.model_settings import save_remote_config
from api.search.profiles import (
    SIGLIP2,
    EmbeddingProfile,
    activate_profile,
    active_profile,
)
from api.tests.utils import create_test_photo, create_test_user


@override_config(CAPTIONING_MODEL="lfm2_vl_450m", EMBEDDING_MODEL="openclip_vitb32")
class RemoteModelSettingsTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.admin = create_test_user(is_admin=True)
        self.client.force_authenticate(self.admin)
        patcher = patch(
            "api.views.site_settings.do_all_models_exist", return_value=True
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_then_reload_never_returns_token(self) -> None:
        response = self.client.post(
            "/api/sitesettings",
            {
                "captioning_model": "openai_api",
                "captioning_api": {
                    "url": "http://vision.example/v1/",
                    "model_name": "vision-model",
                    "token": "secret-token",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["captioning_model"], "openai_api")
        self.assertEqual(
            response.data["captioning_api"]["url"], "http://vision.example/v1"
        )
        self.assertTrue(response.data["captioning_api"]["has_token"])
        for body in (response.data, self.client.get("/api/sitesettings").data):
            self.assertNotIn("secret-token", str(body))
            self.assertNotIn("token", body["captioning_api"])
        config = RemoteModelConfig.objects.get(pk="captioning")
        self.assertEqual(config.token, "secret-token")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT token FROM api_remotemodelconfig WHERE kind = %s",
                ["captioning"],
            )
            raw = cursor.fetchone()[0]
        self.assertNotIn(b"secret-token", bytes(raw))

    def test_blank_token_keeps_secret_and_explicit_clear_removes_it(self) -> None:
        save_remote_config("captioning", {"token": "saved"})
        for values in ({"model_name": "new"}, {"token": ""}):
            self.assertEqual(
                self.client.post(
                    "/api/sitesettings", {"captioning_api": values}, format="json"
                ).status_code,
                200,
            )
            self.assertEqual(
                RemoteModelConfig.objects.get(pk="captioning").token, "saved"
            )
        self.client.post(
            "/api/sitesettings",
            {"captioning_api": {"clear_token": True}},
            format="json",
        )
        self.assertEqual(RemoteModelConfig.objects.get(pk="captioning").token, "")

    def test_non_admin_cannot_read_private_settings_or_write_them(self) -> None:
        save_remote_config(
            "captioning", {"url": "http://private.example/v1", "token": "saved"}
        )
        for user in (None, create_test_user()):
            self.client.force_authenticate(user)
            body = self.client.get("/api/sitesettings").data
            self.assertNotIn("captioning_api", body)
            self.assertNotIn("embedding_api", body)
            if user is None:
                self.assertNotIn("embedding_status", body)
            else:
                self.assertIn("embedding_status", body)
            response = self.client.post(
                "/api/sitesettings",
                {"captioning_api": {"token": "changed"}},
                format="json",
            )
            self.assertIn(response.status_code, (401, 403))
        self.assertEqual(RemoteModelConfig.objects.get(pk="captioning").token, "saved")

    def test_unsafe_base_urls_are_rejected(self) -> None:
        for url in (
            "file:///data/photo.jpg",
            "https://user:password@example.com/v1",
            "http://example.com/v1?token=secret",
            "http://example.com/#fragment",
        ):
            with self.subTest(url=url):
                response = self.client.post(
                    "/api/sitesettings", {"captioning_api": {"url": url}}, format="json"
                )
                self.assertEqual(response.status_code, 400)

    def test_remote_provider_requires_url_and_model(self) -> None:
        for field, value in (
            ("captioning_model", "openai_api"),
            ("embedding_model", SIGLIP2),
        ):
            response = self.client.post(
                "/api/sitesettings", {field: value}, format="json"
            )
            self.assertEqual(response.status_code, 400)

    def test_rotating_embedding_token_updates_active_profile_without_reindexing(
        self,
    ) -> None:
        profile = EmbeddingProfile(
            SIGLIP2,
            "http://embed.example/v1",
            "siglip2-so400m-patch16-naflex",
            token="old",
        )
        activate_profile(self.admin, profile)
        response = self.client.post(
            "/api/sitesettings",
            {
                "embedding_api": {
                    "url": profile.url,
                    "model_name": profile.model_name,
                    "token": "new",
                }
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        current = active_profile(self.admin)
        self.assertEqual(current.key, profile.key)
        self.assertEqual(current.token, "new")

    @patch("api.views.site_settings.start_model_download")
    def test_admin_can_start_a_rebuild_and_see_its_progress(self, _download) -> None:
        with patch(
            "api.runtime.ml_models.missing_models_prerequisites", return_value=[]
        ):
            response = self.client.post(
                "/api/sitesettings", {"rebuild_embeddings": True}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        job = response.data["embedding_status"]["job"]
        self.assertEqual(job["status"], "running")


@override_config(EMBEDDING_MODEL=SIGLIP2)
class EmbeddingChangeNoticeTest(TestCase):
    def setUp(self) -> None:
        self.user = create_test_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        save_remote_config(
            "embeddings",
            {
                "url": "http://embed.example/v1",
                "model_name": "siglip2-so400m-patch16-naflex",
            },
        )
        from api.search.profiles import selected_profile

        self.profile = selected_profile()
        activate_profile(self.user, self.profile)

    def test_vector_profile_changes_require_rebuild_without_changing_active_index(
        self,
    ) -> None:
        changes = (
            {"revision": "checkpoint-2"},
            {"url": "http://other.example/v1"},
            {"model_name": "other-model"},
            {"max_num_patches": 1024},
        )
        for change in changes:
            with self.subTest(change=change):
                save_remote_config(
                    "embeddings", {**self.profile.specification, **change}
                )
                status = self.client.get("/api/sitesettings").data["embedding_status"]
                self.assertTrue(status["reindex_required"])
                self.assertEqual(active_profile(self.user).key, self.profile.key)
        with override_config(EMBEDDING_MODEL="openclip_vitb32"):
            self.assertTrue(
                self.client.get("/api/sitesettings").data["embedding_status"][
                    "reindex_required"
                ]
            )
            self.assertEqual(active_profile(self.user).key, self.profile.key)

    def test_credentials_and_thresholds_do_not_require_vector_rebuild(self) -> None:
        save_remote_config(
            "embeddings",
            {
                "token": "rotated",
                "search_threshold": 0.2,
                "similar_threshold": 0.9,
                "tag_threshold": 0.3,
            },
        )
        response = self.client.get("/api/sitesettings")
        self.assertFalse(response.data["embedding_status"]["reindex_required"])
        self.assertNotIn("embedding_api", response.data)
        self.assertNotIn("rotated", str(response.data))

    def test_each_user_sees_their_own_active_index(self) -> None:
        other = create_test_user()
        self.client.force_authenticate(other)
        status = self.client.get("/api/sitesettings").data["embedding_status"]
        self.assertTrue(status["reindex_required"])
        self.assertEqual(status["active_model"], "openclip_vitb32")

    def test_revision_change_at_same_endpoint_pauses_text_search_until_rebuild(
        self,
    ) -> None:
        from api.search.profiles import selected_profile, text_search_paused

        save_remote_config("embeddings", {"revision": "checkpoint-2"})
        self.assertTrue(text_search_paused(active_profile(self.user)))
        status = self.client.get("/api/sitesettings").data["embedding_status"]
        self.assertTrue(status["text_search_paused"])
        activate_profile(self.user, selected_profile())
        self.assertFalse(
            self.client.get("/api/sitesettings").data["embedding_status"][
                "text_search_paused"
            ]
        )

    def test_changed_revision_never_encodes_text_against_the_old_index(self) -> None:
        self.user.semantic_search_topk = 10
        self.user.save(update_fields=["semantic_search_topk"])
        photo = create_test_photo(
            owner=self.user, captions_json={"user_caption": "dog portrait"}
        )
        photo.caption_instance.apply_user_caption("dog portrait")
        save_remote_config("embeddings", {"revision": "checkpoint-2"})
        with patch("api.search.filters.remote_embeddings") as encode:
            response = self.client.get("/api/photos/searchlist/?search=dog")
        self.assertEqual(response.status_code, 200)
        encode.assert_not_called()
        self.assertIn(
            photo.image_hash, [row["image_hash"] for row in response.data["results"]]
        )
