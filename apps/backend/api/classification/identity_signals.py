"""Observe identity changes without running a VLM inside a model signal."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from django.db.models import Q
from django.db.models.signals import (
    m2m_changed,
    post_delete,
    post_save,
    pre_delete,
    pre_save,
)

from api.classification.identity_updates import defer_caption_updates
from api.models.face import Face
from api.models.person import Person
from api.models.photo import Photo
from api.models.user import User

FACE_FIELDS = frozenset(
    {
        "photo",
        "photo_id",
        "person",
        "person_id",
        "classification_person",
        "classification_person_id",
        "classification_probability",
        "cluster_person",
        "cluster_person_id",
        "cluster_probability",
        "deleted",
        "location_top",
        "location_bottom",
        "location_left",
        "location_right",
        "encoding",
        "unmatched_by",
        "video_time",
    }
)
PERSON_FIELDS = frozenset(
    {"name", "kind", "cluster_owner", "cluster_owner_id", "birth_date"}
)


def face_changed(
    sender: type[Face],
    instance: Face,
    update_fields: Iterable[str] | None = None,
    raw: bool = False,
    **kwargs: object,
) -> None:
    if not raw and (update_fields is None or FACE_FIELDS.intersection(update_fields)):
        defer_caption_updates((instance.photo_id,))


def person_photos(person_id: int, user_id: int | None) -> tuple[uuid.UUID, ...]:
    user = User.objects.filter(pk=user_id).first() if user_id is not None else None
    if user is None:
        return ()
    return tuple(
        Face.objects.owned_by(user)
        .filter(
            Q(person_id=person_id)
            | Q(classification_person_id=person_id)
            | Q(cluster_person_id=person_id)
        )
        .exclude(photo__isnull=True)
        .values_list("photo_id", flat=True)
        .distinct()
    )


def person_before_save(
    sender: type[Person],
    instance: Person,
    update_fields: Iterable[str] | None = None,
    raw: bool = False,
    **kwargs: object,
) -> None:
    setattr(instance, "_identity_caption_photos", ())
    if (
        raw
        or not instance.pk
        or (update_fields is not None and not PERSON_FIELDS.intersection(update_fields))
    ):
        return
    old = (
        Person.objects.filter(pk=instance.pk)
        .values("name", "kind", "cluster_owner_id", "birth_date")
        .first()
    )
    if old is not None and (
        old["name"] != instance.name
        or old["kind"] != instance.kind
        or old["cluster_owner_id"] != instance.cluster_owner_id
        or old["birth_date"] != instance.birth_date
    ):
        setattr(
            instance,
            "_identity_caption_photos",
            person_photos(instance.pk, old["cluster_owner_id"]),
        )


def person_saved(sender: type[Person], instance: Person, **kwargs: object) -> None:
    value: object = getattr(instance, "_identity_caption_photos", ())
    if isinstance(value, tuple):
        defer_caption_updates(item for item in value if isinstance(item, uuid.UUID))


def person_deleted(sender: type[Person], instance: Person, **kwargs: object) -> None:
    defer_caption_updates(person_photos(instance.pk, instance.cluster_owner_id))


def user_before_save(
    sender: type[User],
    instance: User,
    update_fields: Iterable[str] | None = None,
    raw: bool = False,
    **kwargs: object,
) -> None:
    setattr(instance, "_identity_caption_changed", False)
    if (
        raw
        or not instance.pk
        or (
            update_fields is not None
            and not {"llm_settings", "confidence_person"}.intersection(update_fields)
        )
    ):
        return
    old = (
        User.objects.filter(pk=instance.pk)
        .values("llm_settings", "confidence_person")
        .first()
    )
    if old is not None:
        setattr(
            instance,
            "_identity_caption_changed",
            (
                old["llm_settings"] != instance.llm_settings
                or old["confidence_person"] != instance.confidence_person
            ),
        )


def user_saved(sender: type[User], instance: User, **kwargs: object) -> None:
    if getattr(instance, "_identity_caption_changed", False):
        defer_caption_updates(
            Photo.objects.owned_by(instance)
            .filter(caption_instance__captions_json__im2txt__isnull=False)
            .values_list("pk", flat=True)
        )


def rejected_changed(
    sender: object,
    instance: Face | Person,
    action: str,
    reverse: bool,
    pk_set: set[int] | None = None,
    **kwargs: object,
) -> None:
    if action not in {"post_add", "post_remove", "pre_clear"}:
        return
    if isinstance(instance, Face):
        defer_caption_updates((instance.photo_id,))
    elif instance.cluster_owner_id is not None:
        faces = Face.objects.owned_by(instance.cluster_owner)
        faces = (
            faces.filter(pk__in=pk_set)
            if pk_set is not None
            else faces.filter(rejected_persons=instance)
        )
        defer_caption_updates(faces.values_list("photo_id", flat=True))


def register() -> None:
    pre_save.connect(
        person_before_save,
        sender=Person,
        dispatch_uid="api.classification.identity_signals.person_before_save",
    )
    post_save.connect(
        person_saved,
        sender=Person,
        dispatch_uid="api.classification.identity_signals.person_saved",
    )
    pre_delete.connect(
        person_deleted,
        sender=Person,
        dispatch_uid="api.classification.identity_signals.person_deleted",
    )
    pre_save.connect(
        user_before_save,
        sender=User,
        dispatch_uid="api.classification.identity_signals.user_before_save",
    )
    post_save.connect(
        user_saved,
        sender=User,
        dispatch_uid="api.classification.identity_signals.user_saved",
    )
    post_save.connect(
        face_changed,
        sender=Face,
        dispatch_uid="api.classification.identity_signals.face_saved",
    )
    post_delete.connect(
        face_changed,
        sender=Face,
        dispatch_uid="api.classification.identity_signals.face_deleted",
    )
    m2m_changed.connect(
        rejected_changed,
        sender=Face.rejected_persons.through,
        dispatch_uid="api.classification.identity_signals.rejected_changed",
    )
