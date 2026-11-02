"""Resumable remote embedding jobs and the active-index status for admin."""

from __future__ import annotations

import logging
from collections.abc import Callable

from constance import config as site_config
from django.db import transaction
from django.db.models import F, QuerySet

from api.models import LongRunningJob, Photo, PhotoCaption, PhotoEmbedding, User
from api.models.long_running_job import JobCancelledError
from api.runtime.features import feature_enabled
from api.runtime.remote_inference import RemoteInferenceError
from api.search.profiles import (
    SIGLIP2,
    EmbeddingProfile,
    activate_profile,
    active_profile,
    selected_profile,
    store_profile,
    text_search_paused,
)
from api.search.remote_embeddings import embed_images, labels_for
from api.search.semantic import OPENCLIP

logger = logging.getLogger(__name__)
BATCH_SIZE = 16


def embedding_status(user: User) -> dict[str, object]:
    active = active_profile(user)
    try:
        pending = selected_profile().key != active.key
    except RemoteInferenceError:
        pending = True
    job = (
        LongRunningJob.objects.owned_by(user)
        .filter(
            job_type=LongRunningJob.JOB_CALCULATE_CLIP_EMBEDDINGS,
        )
        .order_by("-queued_at")
        .first()
    )
    status = None
    if job is not None:
        state = (
            "cancelled"
            if job.cancelled
            else "failed"
            if job.failed
            else "finished"
            if job.finished
            else "running"
        )
        status = {
            "id": job.pk,
            "status": state,
            "progress_current": job.progress_current,
            "progress_target": job.progress_target,
        }
    return {
        "selected_model": site_config.EMBEDDING_MODEL,
        "active_model": active.provider,
        "reindex_required": pending,
        "text_search_paused": text_search_paused(active),
        "job": status,
    }


def _missing(user: User, profile: EmbeddingProfile) -> QuerySet[Photo]:
    stored = (
        PhotoEmbedding.objects.owned_by(user)
        .filter(space_id=profile.key, source_hash=F("photo__image_hash"))
        .values("photo_id")
    )
    return Photo.objects.owned_by(user).exclude(pk__in=stored).order_by("pk")


def _cache_photos(
    profile: EmbeddingProfile, photos: list[Photo], with_tags: bool
) -> None:
    space = store_profile(profile)
    paths = []
    for photo in photos:
        thumbnail = getattr(photo, "thumbnail", None)
        if thumbnail is None or not thumbnail.thumbnail_big:
            raise RemoteInferenceError(
                "Some photos have no thumbnail. Complete the library scan before rebuilding embeddings."
            )
        paths.append(thumbnail.thumbnail_big.path)
    vectors = embed_images(profile, paths)
    for photo, vector in zip(photos, vectors, strict=True):
        labels = labels_for(profile, vector) if with_tags else []
        PhotoEmbedding.objects.update_or_create(
            photo=photo,
            space=space,
            defaults={
                "vector": vector,
                "source_hash": photo.image_hash,
                "tags": labels,
                "tagged": with_tags,
            },
        )


def _publish_tags(
    user: User,
    profile: EmbeddingProfile,
    job: LongRunningJob,
    heartbeat: Callable[[], object] | None = None,
) -> None:
    records = (
        PhotoEmbedding.objects.owned_by(user)
        .filter(space_id=profile.key)
        .select_related("photo")
    )
    count = records.count()
    job.update_progress(current=0, target=count, step="Updating generated things")
    for done, record in enumerate(records.iterator(chunk_size=100), start=1):
        job.stop_if_cancelled()
        if not record.tagged:
            record.tags = labels_for(profile, record.vector)
            record.tagged = True
            record.save(update_fields=["tags", "tagged"])
        caption, _ = PhotoCaption.objects.get_or_create(photo=record.photo)
        caption.store_tags(record.tags, model=SIGLIP2)
        if done % 100 == 0 or done == count:
            job.update_progress(current=done, target=count)
            if heartbeat is not None:
                heartbeat()


def run_remote_embedding_job(
    user: User,
    job: LongRunningJob,
    profile: EmbeddingProfile,
    heartbeat: Callable[[], object] | None = None,
) -> None:
    """Keep partial vectors on failure. Promote only a complete replacement."""
    from api.search.similarity import build_image_similarity_index

    try:
        store_profile(profile)
        missing = _missing(user, profile)
        count = missing.count()
        job.update_progress(current=0, target=count)
        done = 0
        with_tags = feature_enabled("SCENE_CLASSIFICATION")
        while photos := list(missing.select_related("thumbnail")[:BATCH_SIZE]):
            job.refresh_from_db(fields=["cancelled"])
            job.stop_if_cancelled()
            _cache_photos(profile, photos, with_tags)
            done += len(photos)
            job.update_progress(current=done, target=count)
            if heartbeat is not None:
                heartbeat()
        job.refresh_from_db(fields=["cancelled"])
        job.stop_if_cancelled()
        build_image_similarity_index(user, profile=profile)
        with transaction.atomic():
            locked = LongRunningJob.objects.select_for_update().get(pk=job.pk)
            locked.stop_if_cancelled()
            activate_profile(user, profile)
        if with_tags:
            _publish_tags(user, profile, job, heartbeat)
        job.complete(
            {
                "provider": profile.provider,
                "embedding_space": profile.key,
                "dimension": profile.dimension,
            }
        )
    except JobCancelledError:
        logger.info(
            "Remote embedding job %s cancelled; cached vectors retained", job.job_id
        )
    except Exception as error:
        job.fail(error)
        logger.exception(
            "Remote embedding job %s failed; previous vectors retained", job.job_id
        )
        raise


def generate_remote_tags(
    caption: PhotoCaption, commit: bool = True, force: bool = False
) -> None:
    profile = selected_profile()
    record = PhotoEmbedding.objects.filter(
        photo=caption.photo, space_id=profile.key
    ).first()
    if record is None or record.source_hash != caption.photo.image_hash:
        _cache_photos(profile, [caption.photo], True)
        record = PhotoEmbedding.objects.get(photo=caption.photo, space_id=profile.key)
    elif force or not record.tagged:
        record.tags = labels_for(profile, record.vector)
        record.tagged = True
        record.save(update_fields=["tags", "tagged"])
    if active_profile(caption.photo.owner).key == profile.key:
        caption.store_tags(record.tags, commit=commit, model=SIGLIP2)


def restore_local_tags(user: User) -> None:
    captions = PhotoCaption.objects.filter(
        Photo.objects.owner_q(user, through="photo__"),
        captions_json__has_key=OPENCLIP,
        captions_json__tagging_model=SIGLIP2,
    )
    for caption in captions.iterator(chunk_size=100):
        data = caption.captions_json or {}
        tags = data.get(OPENCLIP)
        if data.get("tagging_model", OPENCLIP) != OPENCLIP and isinstance(tags, dict):
            caption.store_tags(tags.get("tags", []))
