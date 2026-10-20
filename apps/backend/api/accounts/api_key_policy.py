"""API-key capabilities. Unlisted operations are refused, including new routes."""

from django.http import HttpRequest

READ = "photos:read"
METADATA_WRITE = "metadata:write"
ALBUMS_WRITE = "albums:write"
JOBS_READ = "jobs:read"
JOBS_SUBMIT = "jobs:submit"
PERMISSIONS = (READ, METADATA_WRITE, ALBUMS_WRITE, JOBS_READ, JOBS_SUBMIT)
DEFAULT_PERMISSIONS = (READ, JOBS_READ)

# Exact view identities and methods prevent a new GET job trigger or account
# endpoint from silently inheriting access from a read-only key.
READ_VIEWS = frozenset(
    {
        "photos.PhotoViewSet",
        "photos.RecentlyAddedPhotoListViewSet",
        "photos.NoTimestampPhotoViewSet",
        "photos.NoLocationPhotoViewSet",
        "search.SearchListViewSet",
        "search.MetadataValuesView",
        "search.SearchTermExamples",
        "albums.PersonViewSet",
        "albums.AlbumUserListViewSet",
        "albums.AlbumUserViewSet",
        "albums.AlbumDateViewSet",
        "albums.AlbumDateListViewSet",
        "albums.AlbumThingViewSet",
        "albums.AlbumThingListViewSet",
        "albums.AlbumPlaceViewSet",
        "albums.AlbumPlaceListViewSet",
        "photo_metadata.PhotoMetadataViewSet",
        "tags.TagViewSet",
        "media.UnifiedMediaAccessView",
        "upload.UploadPhotoExists",
    }
)
WRITES: dict[tuple[str, str], str] = {
    ("photo_metadata.PhotoMetadataViewSet", "PATCH"): METADATA_WRITE,
    ("albums.AlbumUserEditViewSet", "POST"): ALBUMS_WRITE,
    ("albums.AlbumUserEditViewSet", "PATCH"): ALBUMS_WRITE,
    ("scan_triggers.ScanPhotosView", "POST"): JOBS_SUBMIT,
    ("scan_triggers.GenerateCaptionsView", "POST"): JOBS_SUBMIT,
}


def required_permission(request: HttpRequest) -> str | None:
    match = request.resolver_match
    view_class = getattr(match.func, "cls", None) if match is not None else None
    if view_class is None or not view_class.__module__.startswith("api.views."):
        return None
    identity = (
        f"{view_class.__module__.removeprefix('api.views.')}.{view_class.__name__}"
    )
    method = request.method or ""
    if method in ("GET", "HEAD", "OPTIONS"):
        if identity == "jobs.LongRunningJobViewSet":
            return JOBS_READ
        if identity in READ_VIEWS:
            return READ
    return WRITES.get((identity, method))
