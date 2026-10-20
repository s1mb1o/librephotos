"""Owner-visible snapshots from a job's bounded recent-photo window."""

from datetime import datetime
from typing import TypedDict
from uuid import UUID

from api.models.long_running_job import (
    RECENT_CAPTION_LIMIT,
    RECENT_PHOTO_LIMIT,
    LongRunningJob,
)
from api.models.photo import Photo
from api.models.user import User


class RecentJobPhoto(TypedDict):
    photo_id: str
    image_hash: str
    caption: str
    status: str
    processed_at: str
    truncated: bool


class RecentJobPhotos(TypedDict):
    finished: bool
    limit: int
    results: list[RecentJobPhoto]


def recent_job_photos(job: LongRunningJob, user: User) -> RecentJobPhotos:
    """Resolve only photos the job owner still owns and can open."""
    result: RecentJobPhotos = {
        "finished": job.finished,
        "limit": RECENT_PHOTO_LIMIT,
        "results": [],
    }
    if job.started_by_id != user.pk or not isinstance(job.recent_photos, list):
        return result
    records: list[RecentJobPhoto] = []
    for raw in job.recent_photos[:RECENT_PHOTO_LIMIT]:
        if not isinstance(raw, dict):
            continue
        photo_id, caption, status, processed_at = (
            raw.get("photo_id"),
            raw.get("caption"),
            raw.get("status"),
            raw.get("processed_at"),
        )
        if (
            not isinstance(photo_id, str)
            or not isinstance(caption, str)
            or not isinstance(status, str)
            or not isinstance(processed_at, str)
        ):
            continue
        try:
            UUID(photo_id)
            if datetime.fromisoformat(processed_at).tzinfo is None:
                continue
        except ValueError:
            continue
        if status not in {"success", "failed", "skipped"}:
            continue
        records.append(
            {
                "photo_id": photo_id,
                "image_hash": "",
                "caption": caption[:RECENT_CAPTION_LIMIT],
                "status": status,
                "processed_at": processed_at,
                "truncated": bool(raw.get("truncated"))
                or len(caption) > RECENT_CAPTION_LIMIT,
            }
        )
    photos = {
        str(photo_id): image_hash
        for photo_id, image_hash in Photo.objects.owned_by(user)
        .filter(
            pk__in=[record["photo_id"] for record in records],
            removed=False,
            in_trashcan=False,
        )
        .values_list("pk", "image_hash")
    }
    seen: set[str] = set()
    for record in records:
        photo_id = record["photo_id"]
        if photo_id in photos and photo_id not in seen:
            result["results"].append({**record, "image_hash": photos[photo_id]})
            seen.add(photo_id)
    return result
