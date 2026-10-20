"""Refresh generated captions after identity evidence changes."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from functools import partial

from django.db import transaction
from django.utils import timezone

from api.classification.identity_context import (
    TOKEN,
    identity_context,
    identity_metadata,
    render_template,
    stored_anchors,
)
from api.jobs.queue import enqueue_task
from api.models.photo import Photo
from api.models.photo_caption import CAPTION_IDENTITY_KEY as IDENTITY_KEY
from api.models.photo_caption import PhotoCaption
from api.models.user import User

logger = logging.getLogger(__name__)


def defer_caption_updates(photo_ids: Iterable[uuid.UUID | None]) -> None:
    ids = tuple(sorted({pk for pk in photo_ids if pk is not None}, key=str))
    if ids:
        transaction.on_commit(partial(invalidate_identity_captions, ids))


def _save(caption: PhotoCaption, data: dict[str, object], text: str) -> None:
    caption.store_generated_caption(data, text, True)
    Photo.objects.filter(pk=caption.photo_id).update(last_modified=timezone.now())


def invalidate_identity_captions(photo_ids: Iterable[uuid.UUID]) -> None:
    """Rebind safe templates immediately. Queue inference only when needed."""
    ids = PhotoCaption.objects.filter(
        photo_id__in=photo_ids, captions_json__im2txt__isnull=False
    ).values_list("pk", flat=True)
    for photo_id in ids.iterator(chunk_size=200):
        with transaction.atomic():
            caption = (
                PhotoCaption.objects.select_for_update()
                .select_related("photo")
                .filter(pk=photo_id)
                .first()
            )
            if caption is None or caption.photo.removed or caption.photo.in_trashcan:
                continue
            data = dict(caption.captions_json or {})
            text = data.get("im2txt")
            if not isinstance(text, str) or not text:
                continue
            context = identity_context(caption.photo)
            saved = data.get(IDENTITY_KEY)
            previous = saved if isinstance(saved, dict) else {}
            if previous.get("context_key") == context.key and not previous.get("stale"):
                continue
            template = previous.get("template")
            anchors = stored_anchors(previous.get("anchors"))
            if isinstance(template, str):
                source_hash = str(previous.get("source_hash", ""))
                text = render_template(template, context, anchors, source_hash)
                referenced = {int(match[1]) for match in TOKEN.finditer(template)}
                missing_reference = any(
                    person.face_id not in referenced for person in context.identities
                )
                if (
                    previous.get("geometry_key") == context.geometry_key
                    and not missing_reference
                ):
                    data[IDENTITY_KEY] = identity_metadata(context, template, anchors)
                    _save(caption, data, text)
                    continue
            pending = previous.get("pending_key") == context.key
            data[IDENTITY_KEY] = {**previous, "stale": True, "pending_key": context.key}
            _save(caption, data, text)
            if not pending:
                transaction.on_commit(
                    partial(
                        enqueue_task,
                        refresh_identity_caption,
                        caption.photo_id,
                        caption.photo.owner_id,
                        context.key,
                    )
                )


def refresh_identity_caption(
    photo_id: uuid.UUID, user_id: int, expected_key: str
) -> None:
    """Ignore superseded tasks and retain retry state after a failed provider."""
    from api.classification.captioning import caption_photo, captioning_available

    user = User.objects.filter(pk=user_id).first()
    caption = (
        PhotoCaption.objects.select_related("photo")
        .filter(photo__in=Photo.objects.owned_by(user), pk=photo_id)
        .first()
    )
    if (
        caption is None
        or not captioning_available()
        or caption.photo.removed
        or caption.photo.in_trashcan
    ):
        return
    saved = (caption.captions_json or {}).get(IDENTITY_KEY)
    if not isinstance(saved, dict) or saved.get("pending_key") != expected_key:
        return
    if identity_context(caption.photo).key != expected_key:
        invalidate_identity_captions((photo_id,))
        return
    try:
        caption_photo(caption)
    except Exception:
        with transaction.atomic():
            current = (
                PhotoCaption.objects.select_for_update().filter(pk=photo_id).first()
            )
            if current is not None:
                data = dict(current.captions_json or {})
                metadata = data.get(IDENTITY_KEY)
                if (
                    isinstance(metadata, dict)
                    and metadata.get("pending_key") == expected_key
                ):
                    data[IDENTITY_KEY] = {
                        **metadata,
                        "stale": True,
                        "pending_key": None,
                    }
                    current.captions_json = data
                    current.save(update_fields=["captions_json", "updated_at"])
        logger.warning("Identity caption refresh failed for photo %s", photo_id)
        raise
