"""Image transport, caption preservation, and errors for the remote provider."""

import base64
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import PIL.Image
import requests
from constance.test import override_config
from django.test import TestCase, override_settings

from api.classification.captioning import (
    CaptionError,
    caption_photo,
    generate_caption,
    generate_photo_caption,
)
from api.runtime.ml_models import captioning_model_prerequisites
from api.runtime.model_settings import save_remote_config
from api.runtime.supervisor import is_service_enabled
from api.tests.utils import create_test_photo, create_test_user


def reply(body: object, status: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    return response


@override_config(CAPTIONING_MODEL="openai_api", IMAGE_CAPTIONING_ENABLED=True)
@override_settings(FEATURE_IMAGE_CAPTIONING=True)
class RemoteCaptioningTest(TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=directory.name))
        self.image = Path(directory.name) / "thumbnail.png"
        PIL.Image.new("RGB", (48, 24), "blue").save(self.image)
        save_remote_config(
            "captioning",
            {
                "url": "http://vision.example/v1",
                "model_name": "vision-model",
                "token": "private-token",
            },
        )

    @patch("api.runtime.remote_inference.requests.post")
    def test_image_bytes_prompt_and_token_reach_provider(self, post) -> None:
        post.return_value = reply(
            {"choices": [{"message": {"content": "  A blue sky.  "}}]}
        )
        self.assertEqual(
            generate_caption(str(self.image), "Describe Olga by the lake."),
            "A blue sky.",
        )
        self.assertEqual(
            post.call_args.args[0], "http://vision.example/v1/chat/completions"
        )
        request = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(request["model"], "vision-model")
        content = request["messages"][0]["content"]
        self.assertEqual(content[0]["text"], "Describe Olga by the lake.")
        image = content[1]["image_url"]["url"]
        self.assertTrue(image.startswith("data:image/jpeg;base64,"))
        with PIL.Image.open(
            io.BytesIO(base64.b64decode(image.split(",", 1)[1]))
        ) as decoded:
            self.assertEqual(decoded.size, (48, 24))
        self.assertNotIn(str(self.image), post.call_args.kwargs["data"])
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"], "Bearer private-token"
        )
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        self.assertEqual(post.call_args.kwargs["timeout"], (10, 180))

    @patch("api.runtime.remote_inference.requests.post")
    def test_vllm_thinking_extension_is_explicit_and_optional(self, post) -> None:
        post.return_value = reply({"choices": [{"message": {"content": "Blue sky."}}]})
        generate_caption(str(self.image))
        self.assertNotIn(
            "chat_template_kwargs", json.loads(post.call_args.kwargs["data"])
        )
        save_remote_config("captioning", {"disable_thinking": True})
        generate_caption(str(self.image))
        self.assertEqual(
            json.loads(post.call_args.kwargs["data"])["chat_template_kwargs"],
            {"enable_thinking": False},
        )

    @patch("api.runtime.remote_inference.requests.post")
    def test_caption_storage_preserves_manual_caption_and_search(self, post) -> None:
        post.return_value = reply(
            {"choices": [{"message": {"content": "A sailboat on a lake."}}]}
        )
        user = create_test_user()
        photo = create_test_photo(
            owner=user,
            thumbnail_big=self.image.name,
            captions_json={"user_caption": "My holiday"},
        )
        caption_photo(photo.caption_instance)
        photo.caption_instance.refresh_from_db()
        self.assertEqual(
            photo.caption_instance.captions_json["captioning"],
            {
                "provider": "openai_api",
                "model": "vision-model",
                "source_hash": photo.image_hash,
            },
        )
        self.assertEqual(
            photo.caption_instance.captions_json["user_caption"], "My holiday"
        )
        self.assertEqual(
            photo.caption_instance.captions_json["im2txt"], "A sailboat on a lake."
        )
        self.assertIn("sailboat", photo.search_instance.search_captions)

    @patch("api.runtime.remote_inference.requests.post")
    def test_failed_provider_does_not_replace_existing_caption_or_leak_token(
        self, post
    ) -> None:
        post.return_value = reply({"error": "private-token was rejected"}, 401)
        photo = create_test_photo(
            owner=create_test_user(),
            thumbnail_big=self.image.name,
            captions_json={"im2txt": "Existing", "user_caption": "Manual"},
        )
        with self.assertLogs("api.classification.captioning", level="ERROR") as logs:
            self.assertFalse(generate_photo_caption(photo.caption_instance))
        self.assertNotIn("private-token", "\n".join(logs.output))
        self.assertIn("HTTP 401", "\n".join(logs.output))
        photo.caption_instance.refresh_from_db()
        self.assertEqual(
            photo.caption_instance.captions_json,
            {"im2txt": "Existing", "user_caption": "Manual"},
        )

    @patch("api.runtime.remote_inference.requests.post")
    def test_empty_or_invalid_replies_fail_with_actionable_errors(self, post) -> None:
        for body in (
            {},
            {"choices": []},
            {"choices": [{"message": {"content": None}}]},
            {"choices": [{"message": {"content": " "}}]},
        ):
            with self.subTest(body=body):
                post.return_value = reply(body)
                with self.assertRaisesMessage(CaptionError, "no caption text"):
                    generate_caption(str(self.image))

    @patch("api.runtime.remote_inference.requests.post")
    def test_keyless_provider_omits_authorization(self, post) -> None:
        save_remote_config("captioning", {"clear_token": True})
        post.return_value = reply({"choices": [{"message": {"content": "Caption"}}]})
        generate_caption(str(self.image))
        self.assertNotIn("Authorization", post.call_args.kwargs["headers"])

    @patch(
        "api.runtime.remote_inference.requests.post",
        side_effect=requests.Timeout("private-token"),
    )
    def test_timeout_is_sanitized(self, _post) -> None:
        with self.assertRaisesMessage(CaptionError, "timed out") as error:
            generate_caption(str(self.image))
        self.assertNotIn("private-token", str(error.exception))

    def test_remote_provider_needs_no_local_caption_sidecar_or_model_download(
        self,
    ) -> None:
        self.assertFalse(is_service_enabled("image_captioning"))
        self.assertEqual(captioning_model_prerequisites(create_test_user()), [])
