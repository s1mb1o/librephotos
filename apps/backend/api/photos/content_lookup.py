"""Read owner-scoped catalog matches for bare file content digests."""

from collections.abc import Collection
from uuid import UUID

from api.models.file import content_hash, hash_for_owner
from api.models.photo import Photo
from api.models.user import User

MAX_FILE_LOOKUP = 100


def find_photo_ids(user: User, md5s: Collection[str]) -> dict[str, UUID]:
    """Match the same hashes and first photo as the single-file lookup."""
    keys = set(md5s) | {hash_for_owner(digest, user.pk) for digest in md5s}
    photos = Photo.objects.owned_by(user).order_by()
    # Separate indexed predicates avoid an OR across the photo/file join.
    historical = photos.filter(image_hash__in=keys).values_list("image_hash", "pk")
    current = photos.filter(files__hash__in=keys).values_list("files__hash", "pk")
    found: dict[str, UUID] = {}
    for file_hash, photo_id in historical.union(current, all=True):
        digest = content_hash(file_hash)
        previous = found.get(digest)
        if previous is None or photo_id < previous:
            found[digest] = photo_id
    return found
