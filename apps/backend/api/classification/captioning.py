"""Caption a photo with the selected local or remote provider."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import requests
from constance import config as site_config

from api.models.user import User
from api.runtime import sidecars
from api.runtime.features import feature_enabled
from api.runtime.http_timeouts import CAPTION
from api.runtime.ml_models import captioning_model_selected

if TYPE_CHECKING:
    from api.models.photo_caption import PhotoCaption
    from api.models.remote_model import RemoteModelConfig

logger = logging.getLogger(__name__)


class CaptionError(RuntimeError):
    """The captioning sidecar answered, but not with a caption."""


def generate_caption(
    image_path: str,
    prompt: str | None = None,
    *,
    remote_config: RemoteModelConfig | None = None,
) -> str:
    """A caption from the selected local or OpenAI-compatible provider.

    ``prompt`` steers the vision-language model. ``None`` requests a short
    caption. Remote failures become sanitized ``CaptionError`` messages.
    Local sidecar errors retain the existing error details and timeouts.
    """
    if remote_config is not None or site_config.CAPTIONING_MODEL == "openai_api":
        from api.classification.openai_captioning import generate_remote_caption
        from api.runtime.remote_inference import RemoteInferenceError

        try:
            return generate_remote_caption(image_path, prompt, remote_config)
        except RemoteInferenceError as error:
            raise CaptionError(str(error)) from None

    json_data = {"image_path": image_path}
    if prompt is not None:
        json_data["prompt"] = prompt

    try:
        response = sidecars.post(
            "image_captioning", "/generate-caption", json=json_data, timeout=CAPTION
        )
    except requests.HTTPError as error:
        failed = error.response
        # sidecars.post raises only through raise_for_status(), which always
        # attaches the response.
        assert failed is not None
        raise CaptionError(
            f"captioning sidecar returned HTTP {failed.status_code}: {_detail(failed)}"
        ) from error

    body = _body(response)
    if "caption" not in body:
        raise CaptionError(
            f"captioning sidecar returned HTTP {response.status_code}: "
            f"{_detail(response)}"
        )
    return body["caption"]


def _body(response: requests.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _detail(response: requests.Response) -> str:
    return (
        _body(response).get("error") or response.text.strip() or "no caption in reply"
    )


def captioning_available() -> bool:
    """Whether captions may be generated now.

    The ``IMAGE_CAPTIONING`` feature is on (environment flag and site switch)
    and an admin picked a captioning model; "None" turns captioning off.
    """
    return feature_enabled("IMAGE_CAPTIONING") and captioning_model_selected()


def caption_photo(caption: PhotoCaption, commit: bool = True) -> str:
    """Caption the photo with the captioning sidecar and store it; the caption.

    The prompt carries the recognised person and the place when the user's
    caption settings allow it. Stored as ``captions_json["im2txt"]`` (the
    first model's name); the user's own ``user_caption`` is never touched.
    Raises ``CaptionError`` when the photo has no readable big thumbnail or
    the sidecar answers without a caption; connection errors propagate.
    Does not check whether captioning is on: see ``captioning_available``.
    """
    image_hash = caption.photo.image_hash
    image_path = caption.resolve_thumbnail_path()
    if image_path is None:
        raise CaptionError(f"photo {image_hash} has no thumbnail to caption")

    llm_settings = User.objects.get(username=caption.photo.owner).llm_settings
    prompt = caption.caption_prompt(caption.caption_context(llm_settings))
    logger.debug("Caption prompt: %s", prompt)

    remote = None
    if site_config.CAPTIONING_MODEL == "openai_api":
        from api.runtime.model_settings import remote_config

        remote = remote_config("captioning")
    text = (
        generate_caption(image_path=image_path, prompt=prompt, remote_config=remote)
        if remote is not None
        else generate_caption(image_path=image_path, prompt=prompt)
    )
    text = text.replace("<start>", "").replace("<end>", "").strip()

    if caption.captions_json is None:
        caption.captions_json = {}
    if remote is not None:
        caption.captions_json["captioning"] = {
            "provider": "openai_api",
            "model": remote.model_name,
            "source_hash": image_hash,
        }
    caption.store_generated_caption(caption.captions_json, text, commit)

    logger.info("generated a caption for photo %s", image_hash)
    logger.debug("caption for photo %s: %s", image_hash, text)
    return text


def generate_photo_caption(caption: PhotoCaption, commit: bool = True) -> bool:
    """``caption_photo`` when captioning is on; whether a caption was stored.

    Moved out of ``PhotoCaption`` so the model makes no sidecar calls
    (#2336). Errors are logged, not raised.
    """
    if not captioning_available():
        logger.info("Image captioning is disabled")
        return False

    try:
        caption_photo(caption, commit)
    except Exception:
        logger.exception(
            "could not generate a caption for photo %s", caption.photo.image_hash
        )
        return False
    return True
