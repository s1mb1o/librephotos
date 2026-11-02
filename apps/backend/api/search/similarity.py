import logging
from collections.abc import Sequence
from datetime import datetime
from math import ceil
from typing import TYPE_CHECKING, TypedDict
from uuid import UUID

import requests
from django.db.models import F

from api.lazy_import import LazyModule
from api.models import Photo, User
from api.models.remote_model import PhotoEmbedding
from api.runtime import sidecars
from api.runtime.http_timeouts import SIMILARITY
from api.runtime.model_settings import remote_config
from api.search.profiles import EmbeddingProfile, active_profile
from api.search.semantic import (
    OPENCLIP,
    SEARCH_THRESHOLD,
    SIMILAR_THRESHOLD,
    is_current_embedding,
    produced_by_openclip,
)

if TYPE_CHECKING:
    import numpy as np
else:
    np = LazyModule("numpy")

logger = logging.getLogger(__name__)


class SimilarPhotosReply(TypedDict):
    """The sidecar's JSON answer to a successful /search/: hashes in result."""

    status: bool
    result: list[str]


# Embeddings per request of an index rebuild.
INDEX_PAGE_SIZE = 5000


def search_similar_embedding(
    user: User | int,
    emb: Sequence[float],
    result_count: int = 100,
    threshold: float | None = None,
    profile: EmbeddingProfile | None = None,
) -> list[str]:
    """Return matches, retaining metadata-search fallback for existing clients."""
    return _embedding_search(
        _embedding_payload(user, emb, result_count, threshold, profile)
    )


def search_similar_embedding_strict(
    user: User | int,
    emb: Sequence[float],
    result_count: int,
    profile: EmbeddingProfile,
) -> list[str]:
    """Require an available index for an explicitly semantic automation request."""
    return _embedding_search(
        _embedding_payload(user, emb, min(1000, result_count), None, profile),
        strict=True,
    )


def _embedding_payload(
    user: User | int,
    emb: Sequence[float],
    result_count: int,
    threshold: float | None,
    profile: EmbeddingProfile | None,
) -> dict[str, object]:
    user_id = user if isinstance(user, int) else user.id
    profile = profile or active_profile(user_id)
    if threshold is None:
        threshold = (
            SEARCH_THRESHOLD
            if profile.provider == OPENCLIP
            else remote_config("embeddings").search_threshold
        )
    return {
        "user_id": user_id,
        "image_embedding": np.array(emb, dtype=np.float32).tolist(),
        "n": result_count,
        "threshold": threshold,
        **profile.index_parameters,
    }


def _embedding_search(post_data: dict[str, object], strict: bool = False) -> list[str]:
    try:
        res = sidecars.post(
            "image_similarity", "/search/", json=post_data, timeout=SIMILARITY
        )
        if strict:
            res.raise_for_status()
    except requests.RequestException as error:
        logger.error(
            "error retrieving similar embeddings for user %s: %s",
            post_data["user_id"],
            sidecars.error_detail(error),
        )
        if strict:
            raise SimilarityIndexError("Similarity service is unavailable.") from None
        return []
    if strict:
        return strict_similarity_reply(res.json())
    return res.json()["result"]


def search_similar_image(
    user: User | int,
    photo: Photo,
    threshold: float | None = None,
    result_count: int | None = None,
    strict: bool = False,
) -> SimilarPhotosReply | list[str]:
    """The user's photos similar to ``photo``.

    A photo whose embedding comes from an earlier model (not converted yet)
    has none: its vector cannot be compared with the index.
    """
    if isinstance(user, int):
        user_id = user
    else:
        user_id = user.id

    profile = active_profile(user_id)
    if profile.provider == OPENCLIP:
        clip_embeddings = (
            photo.get_clip_embeddings() if is_current_embedding(photo) else None
        )
    else:
        record = PhotoEmbedding.objects.filter(
            photo=photo, space_id=profile.key, source_hash=photo.image_hash
        ).first()
        clip_embeddings = record.vector if record is not None else None
    if clip_embeddings is None:
        return []
    if threshold is None:
        threshold = (
            SIMILAR_THRESHOLD
            if profile.provider == OPENCLIP
            else remote_config("embeddings").similar_threshold
        )

    image_embedding = np.array(clip_embeddings, dtype=np.float32)

    post_data = {
        "user_id": user_id,
        "image_embedding": image_embedding.tolist(),
        "threshold": threshold,
        **profile.index_parameters,
    }
    if result_count is not None:
        post_data["n"] = min(1000, max(1, result_count))
    try:
        res = sidecars.post(
            "image_similarity", "/search/", json=post_data, timeout=SIMILARITY
        )
        if strict:
            res.raise_for_status()
    # As above: an unreachable sidecar must not fail the photo detail request.
    except requests.RequestException as error:
        logger.error(
            "error retrieving similar photos to %s belonging to user %s: %s",
            photo.image_hash,
            user_id,
            sidecars.error_detail(error),
        )
        if strict:
            raise SimilarityIndexError("Similarity service is unavailable.") from None
        return []
    if strict:
        return {"status": True, "result": strict_similarity_reply(res.json())}
    return res.json()


def strict_similarity_reply(payload: object) -> list[str]:
    if not isinstance(payload, dict) or payload.get("status") is False:
        raise SimilarityIndexError("Invalid similarity response.")
    result = payload.get("result")
    if not isinstance(result, list) or any(
        not isinstance(value, str) for value in result
    ):
        raise SimilarityIndexError("Invalid similarity response.")
    return [value for value in result[:1000] if isinstance(value, str)]


class SimilarityIndexError(RuntimeError):
    """The similarity sidecar did not take a page of the index rebuild."""


def build_image_similarity_index(
    user: User, profile: EmbeddingProfile | None = None
) -> int:
    """Rebuild one profile's index from the user's matching cached vectors.

    The default is the active profile. Replacement jobs pass their captured
    profile. Different profiles never share vector dimensions or index files.

    The pages go to the sidecar as one rebuild: the first carries ``begin``,
    the last ``commit``, and the sidecar swaps the new index in only after
    the last one, so searches keep answering from the old index meanwhile and
    a failed rebuild leaves it in place. Raises SimilarityIndexError when the
    sidecar refuses or misses a page.
    """
    profile = profile or active_profile(user)
    if profile.provider != OPENCLIP:
        return _build_remote_index(user, profile)
    logger.info("building similarity index for user %s", user.username)
    start = datetime.now()
    # isnull rather than exclude(clip_embeddings=None): that compares every
    # stored embedding with JSON null, reading each one out of TOAST just to
    # count them. A JSON null left in is skipped below, as an empty one is.
    photos = (
        Photo.objects.owned_by(user)
        .filter(hidden=False, clip_embeddings__isnull=False)
        .filter(produced_by_openclip())
    )
    # An empty queryset still has one (empty) page, so a user without
    # embeddings gets an empty index rather than keeping a stale one.
    last_page = max(1, ceil(photos.count() / INDEX_PAGE_SIZE))

    # Keyset pages on (owner, id), not OFFSET ones: each OFFSET page sorted
    # all of the user's photos again, a parallel full scan per page, three
    # rebuilds per conversion run on a large library (#2868).
    after: UUID | None = None
    index_size = 0
    for page in range(1, last_page + 1):
        page_photos = photos.only("clip_embeddings", "image_hash").order_by("pk")
        if after is not None:
            page_photos = page_photos.filter(pk__gt=after)
        image_hashes: list[str] = []
        image_embeddings: list[list[float]] = []
        for photo in page_photos[:INDEX_PAGE_SIZE]:
            after = photo.pk
            clip_embeddings = photo.get_clip_embeddings()
            if clip_embeddings is not None:
                image_hashes.append(photo.image_hash)
                image_embedding = np.array(clip_embeddings, dtype=np.float32)
                image_embeddings.append(image_embedding.tolist())

        post_data = {
            "user_id": user.id,
            "image_hashes": image_hashes,
            "image_embeddings": image_embeddings,
            "begin": page == 1,
            "commit": page == last_page,
        }
        index_size = _post_build_page(user, page, last_page, post_data)
    elapsed = (datetime.now() - start).total_seconds()
    logger.info(
        "building similarity index of %d photos took %.2f seconds", index_size, elapsed
    )
    return index_size


def _build_remote_index(user: User, profile: EmbeddingProfile) -> int:
    records = PhotoEmbedding.objects.owned_by(user).filter(
        space_id=profile.key, photo__hidden=False, source_hash=F("photo__image_hash")
    )
    last_page = max(1, ceil(records.count() / INDEX_PAGE_SIZE))
    after: UUID | None = None
    size = 0
    for page in range(1, last_page + 1):
        query = records.select_related("photo").order_by("photo_id")
        if after is not None:
            query = query.filter(photo_id__gt=after)
        batch = list(query[:INDEX_PAGE_SIZE])
        size = _post_build_page(
            user,
            page,
            last_page,
            {
                "user_id": user.pk,
                "image_hashes": [r.photo.image_hash for r in batch],
                "image_embeddings": [r.vector for r in batch],
                "begin": page == 1,
                "commit": page == last_page,
                **profile.index_parameters,
            },
        )
        if batch:
            after = batch[-1].photo_id
    return size


def _post_build_page(
    user: User, page: int, last_page: int, post_data: dict[str, object]
) -> int:
    where = f"page {page} of {last_page} of the similarity index of {user.username}"
    try:
        body = sidecars.post(
            "image_similarity", "/build/", json=post_data, timeout=SIMILARITY
        ).json()
    except (requests.RequestException, ValueError) as error:
        raise SimilarityIndexError(
            f"{where} failed: {sidecars.error_detail(error)}"
        ) from error
    if not isinstance(body, dict) or body.get("status") is not True:
        raise SimilarityIndexError(f"{where} was refused: {body!r}")
    return body.get("index_size", 0)
