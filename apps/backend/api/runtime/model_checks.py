"""Test draft remote settings with synthetic input and no persistent changes."""

from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory

import PIL.Image
import PIL.ImageDraw

from api.classification.openai_captioning import generate_remote_caption
from api.runtime.model_settings import preview_remote_config
from api.runtime.remote_inference import RemoteInferenceError
from api.search.profiles import EmbeddingProfile
from api.search.remote_embeddings import embed_images, remote_embeddings
from api.search.semantic import SIGLIP2


def check_remote_model(kind: str, values: Mapping[str, object]) -> dict[str, object]:
    """Verify real image inference. Also verify text input for semantic search."""
    config = preview_remote_config(kind, values)
    if not config.url or not config.model_name:
        raise RemoteInferenceError("Enter an API URL and model name before testing.")
    with TemporaryDirectory(prefix="librephotos-model-test-") as directory:
        path = Path(directory) / "test.jpg"
        with PIL.Image.new("RGB", (128, 64), "white") as image:
            draw = PIL.ImageDraw.Draw(image)
            draw.rectangle((8, 8, 56, 56), fill="red")
            draw.ellipse((72, 8, 120, 56), fill="blue")
            image.save(path, format="JPEG")
        if kind == "captioning":
            generate_remote_caption(
                str(path),
                "Describe the shapes and colors in this image in one short sentence.",
                config,
            )
            return {"kind": kind, "dimension": None}
        profile = EmbeddingProfile(
            SIGLIP2,
            config.url,
            config.model_name,
            config.revision,
            config.max_num_patches,
            config.token,
        )
        embed_images(profile, [str(path)])
        remote_embeddings(profile, ["A red square and a blue circle on white."])
        return {"kind": kind, "dimension": profile.dimension}
