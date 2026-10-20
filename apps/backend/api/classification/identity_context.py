"""Bind caption references to face geometry and trusted identities."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from api.models.face import Face
from api.models.person import Person
from api.models.photo import Photo
from api.models.user import User

MIN_INFERRED_SCORE = 0.99
MAX_FACES = 64
TOKEN = re.compile(r"\[\[face:(\d+)\]\]")


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Anchor:
    face_id: int
    bbox: tuple[int, int, int, int]

    @property
    def token(self) -> str:
        return f"[[face:{self.face_id}]]"

    def record(self) -> dict[str, object]:
        return {"face_id": self.face_id, "bbox": list(self.bbox)}


@dataclass(frozen=True)
class Identity:
    face_id: int
    person_id: int
    name: str
    source: str
    classification_score: float | None
    cluster_score: float | None

    def record(self) -> dict[str, object]:
        return dict(vars(self))


@dataclass(frozen=True)
class IdentityContext:
    source_hash: str
    anchors: tuple[Anchor, ...]
    identities: tuple[Identity, ...]
    naming: bool
    threshold: float

    @property
    def geometry_key(self) -> str:
        return fingerprint(
            {
                "version": 1,
                "source": self.source_hash,
                "anchors": [a.record() for a in self.anchors],
            }
        )

    @property
    def key(self) -> str:
        return fingerprint(
            {
                "geometry": self.geometry_key,
                "naming": self.naming,
                "threshold": self.threshold,
                "people": [
                    (p.face_id, p.person_id, p.name, p.source) for p in self.identities
                ],
            }
        )


def trusted_identity(face: Face, photo: Photo, threshold: float) -> Identity | None:
    """An assigned label, or two agreeing finite scores above a strict floor."""
    person = face.person
    source = "confirmed"
    if person is None:
        scores = (face.classification_probability, face.cluster_probability)
        agrees = (
            face.classification_person_id
            and face.classification_person_id == face.cluster_person_id
        )
        confident = all(
            math.isfinite(score) and threshold <= score <= 1 for score in scores
        )
        if not face.encoding or face.unmatched_by or not agrees or not confident:
            return None
        person = face.classification_person
        source = "inferred_agreement"
    if (
        person is None
        or person.kind != Person.KIND_USER
        or person.cluster_owner_id != photo.owner_id
    ):
        return None
    name = person.name.strip()
    if not name or name == Person.UNKNOWN_PERSON_NAME:
        return None
    if (
        person.birth_date
        and photo.exif_timestamp
        and person.birth_date > photo.exif_timestamp.date()
    ):
        return None
    if any(rejected.pk == person.pk for rejected in face.rejected_persons.all()):
        return None
    return Identity(
        face.pk,
        person.pk,
        name,
        source,
        face.classification_probability
        if math.isfinite(face.classification_probability)
        else None,
        face.cluster_probability if math.isfinite(face.cluster_probability) else None,
    )


def _overlap(first: Anchor, second: Anchor) -> bool:
    a, b = first.bbox, second.bbox
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return union > 0 and intersection / union > 0.5


def identity_context(photo: Photo) -> IdentityContext:
    """Read current owner settings and face evidence. No file or network access."""
    user = (
        User.objects.filter(pk=photo.owner_id).first()
        if photo.owner_id is not None
        else None
    )
    if user is None:
        return IdentityContext(photo.image_hash, (), (), False, MIN_INFERRED_SCORE)
    settings = user.llm_settings
    naming = (
        isinstance(settings, dict)
        and bool(settings.get("enabled", False))
        and bool(settings.get("add_person", False))
    )
    score = user.confidence_person
    threshold = (
        max(MIN_INFERRED_SCORE, score)
        if math.isfinite(score) and 0 <= score <= 1
        else 1.0
    )
    if not naming or photo.video:
        return IdentityContext(photo.image_hash, (), (), naming, threshold)
    faces = list(
        Face.objects.owned_by(user)
        .filter(photo_id=photo.pk, deleted=False, video_time__isnull=True)
        .select_related("person", "classification_person", "cluster_person")
        .prefetch_related("rejected_persons")
        .order_by("pk")[:MAX_FACES]
    )
    anchors = [
        Anchor(
            face.pk,
            (
                face.location_left,
                face.location_top,
                face.location_right,
                face.location_bottom,
            ),
        )
        for face in faces
    ]
    anchors = [
        anchor
        for anchor in anchors
        if 0 <= anchor.bbox[0] < anchor.bbox[2] and 0 <= anchor.bbox[1] < anchor.bbox[3]
    ]
    ambiguous = {
        a.face_id
        for a in anchors
        for b in anchors
        if a.face_id != b.face_id and _overlap(a, b)
    }
    anchors = [a for a in anchors if a.face_id not in ambiguous]
    available = {a.face_id for a in anchors}
    identities = [
        identity
        for face in faces
        if face.pk in available
        and (identity := trusted_identity(face, photo, threshold)) is not None
    ]
    # A prediction that duplicates another face's identity in one photo is ambiguous.
    confirmed = {
        identity.person_id for identity in identities if identity.source == "confirmed"
    }
    inferred_ids = [
        identity.person_id for identity in identities if identity.source != "confirmed"
    ]
    identities = [
        identity
        for identity in identities
        if identity.source == "confirmed"
        or (
            identity.person_id not in confirmed
            and inferred_ids.count(identity.person_id) == 1
        )
    ]
    return IdentityContext(
        photo.image_hash, tuple(anchors), tuple(identities), naming, threshold
    )


def stored_anchors(value: object) -> tuple[Anchor, ...]:
    result = []
    if not isinstance(value, list):
        return ()
    for row in value:
        if not isinstance(row, dict):
            continue
        face_id, bbox = row.get("face_id"), row.get("bbox")
        if (
            isinstance(face_id, int)
            and not isinstance(face_id, bool)
            and isinstance(bbox, list)
            and len(bbox) == 4
            and all(isinstance(v, int) and not isinstance(v, bool) for v in bbox)
        ):
            result.append(Anchor(face_id, (bbox[0], bbox[1], bbox[2], bbox[3])))
    return tuple(result)


def render_template(
    template: str, context: IdentityContext, anchors: Sequence[Anchor], source_hash: str
) -> str:
    current = {a.face_id: a for a in context.anchors}
    grounded = {a.face_id for a in anchors if current.get(a.face_id) == a}
    names = {
        p.face_id: p.name
        for p in context.identities
        if p.face_id in grounded and context.source_hash == source_hash
    }
    rendered = TOKEN.sub(lambda match: names.get(int(match[1]), "a person"), template)
    return (
        rendered[:1].upper() + rendered[1:]
        if template.startswith("[[face:")
        else rendered
    )


def identity_metadata(
    context: IdentityContext, template: str, anchors: Sequence[Anchor]
) -> dict[str, object]:
    referenced = {int(match[1]) for match in TOKEN.finditer(template)}
    return {
        "version": 1,
        "source_hash": context.source_hash,
        "geometry_key": context.geometry_key,
        "context_key": context.key,
        "template": template,
        "anchors": [a.record() for a in anchors],
        "resolved_people": [
            p.record()
            for p in context.identities
            if p.face_id in referenced and any(a.face_id == p.face_id for a in anchors)
        ],
        "stale": False,
        "pending_key": None,
    }
