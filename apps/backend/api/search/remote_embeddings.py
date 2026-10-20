"""SigLIP2 vectors and cosine-based labels from an OpenAI-compatible gateway."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import TYPE_CHECKING

from api.lazy_import import LazyModule
from api.runtime.model_settings import remote_config
from api.runtime.remote_inference import RemoteInferenceError, image_data_url, post_json
from api.search.profiles import EmbeddingProfile

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt
else:
    np = LazyModule("numpy")

TEXT_BATCH_SIZE = 128


def remote_embeddings(
    profile: EmbeddingProfile, inputs: list[str]
) -> list[list[float]]:
    """Validate positions and dimensions before returning normalized vectors."""
    if not inputs:
        return []
    body = post_json(
        profile.url,
        profile.token,
        "/embeddings",
        {
            "model": profile.model_name,
            "input": inputs,
            "encoding_format": "float",
            "max_num_patches": profile.max_num_patches,
        },
    )
    rows = body.get("data")
    if (
        body.get("model") != profile.model_name
        or not isinstance(rows, list)
        or len(rows) != len(inputs)
    ):
        raise RemoteInferenceError(
            "The embedding response has an unexpected model or result count."
        )
    ordered: dict[int, list[float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RemoteInferenceError(
                "The embedding response contains an invalid result."
            )
        position, raw = row.get("index"), row.get("embedding")
        if (
            isinstance(position, bool)
            or not isinstance(position, int)
            or position not in range(len(inputs))
            or position in ordered
        ):
            raise RemoteInferenceError(
                "The embedding response has duplicate or invalid positions."
            )
        if (
            not isinstance(raw, list)
            or len(raw) != profile.dimension
            or any(
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or not math.isfinite(v)
                for v in raw
            )
        ):
            raise RemoteInferenceError(
                "The embedding response contains invalid values or incompatible dimensions."
            )
        vector = [float(value) for value in raw]
        norm = math.sqrt(sum(value * value for value in vector))
        if not math.isfinite(norm) or norm <= 1e-12:
            raise RemoteInferenceError(
                "The embedding provider returned a zero or invalid vector."
            )
        ordered[position] = [value / norm for value in vector]
    return [ordered[position] for position in range(len(inputs))]


def embed_images(profile: EmbeddingProfile, paths: list[str]) -> list[list[float]]:
    return remote_embeddings(profile, [image_data_url(path) for path in paths])


@lru_cache(maxsize=4)
def _label_vectors(
    profile: EmbeddingProfile, labels: tuple[str, ...]
) -> npt.NDArray[np.float32]:
    vectors = []
    for start in range(0, len(labels), TEXT_BATCH_SIZE):
        vectors.extend(
            remote_embeddings(
                profile,
                [
                    f"This is a photo of {label}."
                    for label in labels[start : start + TEXT_BATCH_SIZE]
                ],
            )
        )
    return np.asarray(vectors, dtype=np.float32)


def labels_for(profile: EmbeddingProfile, vector: list[float]) -> list[str]:
    # Reuse the built-in vocabulary and custom file. This loads no ONNX model.
    from service.tags.openclip.openclip import OpenCLIP

    labels = tuple(OpenCLIP._load_tags())
    embeddings = _label_vectors(profile, labels)
    threshold = remote_config("embeddings").tag_threshold
    scores = embeddings @ np.asarray(vector, dtype=np.float32)
    scored = list(zip(scores.tolist(), labels, strict=True))
    return [
        label
        for score, label in sorted(scored, reverse=True)[:10]
        if score >= threshold
    ]
