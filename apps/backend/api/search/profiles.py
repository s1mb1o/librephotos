"""Selected and active semantic spaces. Credentials are excluded from identity."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from constance import config as site_config

from api.models import LongRunningJob, Photo, User
from api.models.remote_model import EmbeddingSpace, SemanticIndex
from api.runtime.model_settings import remote_config
from api.runtime.remote_inference import RemoteInferenceError
from api.search.semantic import OPENCLIP, SIGLIP2


@dataclass(frozen=True)
class EmbeddingProfile:
    provider: str = OPENCLIP
    url: str = ""
    model_name: str = OPENCLIP
    revision: str = "laion-datacomp-xl-onnx-v1"
    max_num_patches: int = 256
    token: str = field(default="", repr=False)

    @property
    def dimension(self) -> int:
        return 512 if self.provider == OPENCLIP else 1152

    @property
    def specification(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "url": self.url,
            "model_name": self.model_name,
            "revision": self.revision,
            "max_num_patches": self.max_num_patches,
            "dimension": self.dimension,
            "normalization": "raw" if self.provider == OPENCLIP else "l2",
            "preprocessing": "openclip-onnx-v1"
            if self.provider == OPENCLIP
            else "native-rgb-jpeg90-v1",
        }

    @property
    def key(self) -> str:
        if self.provider == OPENCLIP:
            return OPENCLIP
        return hashlib.sha256(
            json.dumps(self.specification, sort_keys=True).encode()
        ).hexdigest()

    @property
    def index_parameters(self) -> dict[str, object]:
        # Keep the legacy wire contract and its on-disk filename for OpenCLIP.
        return (
            {}
            if self.provider == OPENCLIP
            else {"space": self.key, "dimension": self.dimension}
        )


def selected_profile() -> EmbeddingProfile:
    if site_config.EMBEDDING_MODEL == OPENCLIP:
        return EmbeddingProfile()
    config = remote_config("embeddings")
    if not config.url or not config.model_name:
        raise RemoteInferenceError(
            "Configure the embedding API URL and model name in the admin settings."
        )
    return EmbeddingProfile(
        SIGLIP2,
        config.url,
        config.model_name,
        config.revision,
        config.max_num_patches,
        config.token,
    )


def profile_from_space(space: EmbeddingSpace) -> EmbeddingProfile:
    spec = space.specification
    return EmbeddingProfile(
        provider=str(spec["provider"]),
        url=str(spec["url"]),
        model_name=str(spec["model_name"]),
        revision=str(spec["revision"]),
        max_num_patches=int(spec["max_num_patches"]),
        token=space.token,
    )


def active_profile(user: User | int) -> EmbeddingProfile:
    user_id = user if isinstance(user, int) else user.pk
    index = SemanticIndex.objects.select_related("space").filter(pk=user_id).first()
    return (
        profile_from_space(index.space)
        if index is not None and index.space is not None
        else EmbeddingProfile()
    )


def text_search_paused(profile: EmbeddingProfile) -> bool:
    """A changed checkpoint behind one model name cannot encode old queries."""
    if profile.provider == OPENCLIP:
        return False
    current = remote_config("embeddings")
    return (
        current.url == profile.url
        and current.model_name == profile.model_name
        and current.revision != profile.revision
    )


def store_profile(profile: EmbeddingProfile) -> EmbeddingSpace:
    space, _ = EmbeddingSpace.objects.get_or_create(
        pk=profile.key,
        defaults={"specification": profile.specification, "token": profile.token},
    )
    return space


def activate_profile(user: User, profile: EmbeddingProfile) -> None:
    if profile.provider == OPENCLIP:
        SemanticIndex.objects.owned_by(user).update(space=None)
        return
    space = store_profile(profile)
    SemanticIndex.objects.update_or_create(owner=user, defaults={"space": space})


def local_semantics_required() -> bool:
    """Keep the local encoder while a library still has an active local index."""
    return (
        site_config.EMBEDDING_MODEL == OPENCLIP
        or Photo.objects.filter(
            clip_embeddings_model=OPENCLIP,
            owner__semantic_index__space__isnull=True,
        ).exists()
        or LongRunningJob.objects.filter(
            job_type=LongRunningJob.JOB_CALCULATE_CLIP_EMBEDDINGS,
            finished=False,
            result__provider=OPENCLIP,
        ).exists()
    )
