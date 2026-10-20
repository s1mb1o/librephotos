"""Collect synthetic, authenticated responses from the real REST views."""

import base64
import io
from unittest.mock import patch

import PIL.Image
from django.core.files.base import ContentFile
from django.test import override_settings
from rest_framework.test import APIClient

from api.accounts.api_key_policy import PERMISSIONS
from api.accounts.api_keys import create_api_key
from api.models import AlbumUser, File, LibraryShare, Photo, Tag, User
from api.tests.utils import (
    TEST_MEDIA_ROOT,
    create_test_album_user,
    create_test_face,
    create_test_job,
    create_test_library_share,
    create_test_person,
    create_test_person_share,
    create_test_person_share_photo,
    create_test_photo,
    create_test_user,
)


def collect_mcp_contracts() -> dict[str, object]:
    """Use only test factories and test storage; return no credentials."""
    owner = create_test_user()
    viewer = create_test_user()
    photo = create_test_photo(
        owner=owner,
        captions_json={"user_caption": "A red square"},
        search_captions="/volume1/private/family.jpg Private Person Private Camera",
        camera="Private Camera",
    )
    person = create_test_person(cluster_owner=owner, name="Private Person")
    create_test_face(photo=photo, person=person)
    album = create_test_album_user(owner=owner, title="Contract album")
    job = create_test_job(
        started_by=owner,
        failed=True,
        finished=True,
        result={"errors": ["Cannot read /volume1/Family Photos/a.jpg"]},
    )
    _, secret = create_api_key(owner, "Contract fixture", list(PERMISSIONS))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {secret}")

    def get(path: str) -> object:
        response = client.get(path)
        if response.status_code != 200:
            raise AssertionError((path, response.status_code, response.content))
        return response.json()

    fixtures: dict[str, object] = {}
    fixtures["metadata_write"] = client.patch(
        f"/api/photos/{photo.id}/metadata/",
        {"caption": "A blue square", "keywords": ["contract-keyword"]},
        format="json",
    ).status_code
    response = client.patch(
        f"/api/albums/user/edit/{album.id}/", {"photos": [str(photo.id)]}, format="json"
    )
    if response.status_code != 200 or not album.photos.filter(pk=photo.id).exists():
        raise AssertionError("A UUID album addition did not persist")
    fixtures["album_add"] = response.status_code
    if (
        not Tag.objects.owned_by(owner)
        .filter(photos=photo, name="contract-keyword")
        .exists()
    ):
        raise AssertionError("Keyword edit did not persist")
    fixtures["search"] = get("/api/integrations/search/?page_size=25&semantic=false")
    fixtures["people"] = get("/api/persons/?page_size=25")
    fixtures["albums"] = get("/api/albums/user/list/?page_size=25")
    fixtures["album"] = get(f"/api/integrations/albums/{album.id}/photos/?page_size=25")
    fixtures["job"] = get(f"/api/integrations/jobs/{job.job_id}/")
    if photo.main_file is None:
        raise AssertionError("Missing synthetic file")
    fixtures["content_md5"] = photo.main_file.hash[:32]
    fixtures["exists"] = get(f"/api/exists/{photo.main_file.hash[:32]}/")
    fixtures["preview"] = preview_contract(client, photo)
    fixtures["photo"] = get(f"/api/integrations/photos/{photo.id}/")
    fixtures.update(write_and_video_contracts(client, photo, album, viewer))
    share = create_test_library_share(owner, viewer)
    _, viewer_key = create_api_key(viewer, "Contract viewer")
    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {viewer_key}")
    fixtures["shared_photo_hidden"] = get(f"/api/integrations/photos/{photo.id}/")
    share.share_captions = True
    share.save(update_fields=["share_captions"])
    fixtures["shared_photo_caption"] = get(f"/api/integrations/photos/{photo.id}/")
    fixtures["shared_preview"] = preview_contract(client, photo)
    fixtures.update(shared_contracts(owner, viewer, photo, album, client))
    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {secret}")
    with (
        patch("api.views.scan_triggers.captioning_available", return_value=True),
        patch(
            "api.views.scan_triggers.captioning_model_prerequisites", return_value=[]
        ),
    ):
        started = client.post(
            "/api/generate-captions/", {"full_scan": False}, format="json"
        )
        if started.status_code != 200:
            raise AssertionError((started.status_code, started.content))
        fixtures["caption_job"] = started.json()
    return fixtures


def write_and_video_contracts(
    client: APIClient, photo: Photo, album: AlbumUser, other: User
) -> dict[str, object]:
    """Verify actual write results and serialize a real video summary."""
    fixtures: dict[str, object] = {}
    foreign = create_test_photo(owner=other)
    response = client.patch(
        f"/api/albums/user/edit/{album.id}/",
        {"photos": [str(foreign.id)]},
        format="json",
    )
    if (
        response.status_code not in (400, 403, 404)
        or album.photos.filter(pk=foreign.pk).exists()
    ):
        raise AssertionError("Foreign album additions must be refused")
    fixtures["foreign_album_add"] = response.status_code
    response = client.patch(
        f"/api/albums/user/edit/{album.id}/",
        {"removedPhotos": [photo.image_hash]},
        format="json",
    )
    if response.status_code != 200 or album.photos.filter(pk=photo.pk).exists():
        raise AssertionError("Album removal did not persist")
    fixtures["album_remove"] = response.status_code
    album.photos.add(photo)
    video = create_test_photo(owner=photo.owner, video=True)
    if video.main_file is None:
        raise AssertionError("Video fixture requires a main file")
    video.main_file.type = File.VIDEO
    video.main_file.save(update_fields=["type"])
    response = client.get("/api/integrations/search/?file_type=video&semantic=false")
    fixtures["video_search"] = response.json()
    fixtures["video_photo"] = client.get(f"/api/integrations/photos/{video.id}/").json()
    fixtures["video_preview"] = preview_contract(client, video, still=True)
    photo.owner.scan_directory = TEST_MEDIA_ROOT
    photo.owner.save(update_fields=["scan_directory"])
    with patch("api.views.scan_triggers.missing_models_prerequisites", return_value=[]):
        response = client.post("/api/scanphotos/")
    if response.status_code != 200:
        raise AssertionError((response.status_code, response.content))
    fixtures["scan_job"] = response.json()
    return fixtures


def preview_contract(
    client: APIClient, photo: Photo, still: bool = False
) -> dict[str, str]:
    """Return real authorized image bytes from temporary thumbnail storage."""
    with override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, SERVE_FRONTEND=True):
        buffer = io.BytesIO()
        PIL.Image.new("RGB", (8, 8), "blue").save(buffer, format="WEBP")
        thumbnail = (
            photo.thumbnail.thumbnail_big if still else photo.thumbnail.square_thumbnail
        )
        if not thumbnail.storage.exists(thumbnail.name):
            thumbnail.save(photo.image_hash + ".webp", ContentFile(buffer.getvalue()))
        url = f"/media/thumbnails_big/{photo.image_hash}" if still else thumbnail.url
        preview = client.get(url)
        if preview.status_code != 200:
            raise AssertionError("Authenticated preview failed")
        content = (
            b"".join(preview.streaming_content)
            if preview.streaming
            else preview.content
        )
        result = {
            "mime_type": preview["Content-Type"],
            "data": base64.b64encode(content).decode(),
        }
        return result


def shared_contracts(
    owner: User, viewer: User, photo: Photo, album: AlbumUser, client: APIClient
) -> dict[str, object]:
    """Exercise each indirect sharing path with metadata grants disabled."""
    LibraryShare.objects.owned_by(owner).delete()
    album.members_share_captions = False
    album.members_share_faces = False
    album.save(update_fields=["members_share_captions", "members_share_faces"])
    album.shared_to.add(viewer)
    fixtures: dict[str, object] = {}
    paths = {
        "member_photo": f"/api/integrations/photos/{photo.id}/",
        "member_album": f"/api/integrations/albums/{album.id}/photos/",
    }
    for name, path in paths.items():
        response = client.get(path)
        if response.status_code != 200:
            raise AssertionError((name, response.status_code))
        fixtures[name] = response.json()
    album.shared_to.remove(viewer)
    person = create_test_person(cluster_owner=owner, name="Shared Person")
    create_test_face(photo=photo, person=person)
    create_test_person_share(person, viewer)
    create_test_person_share_photo(person, photo)
    response = client.get(f"/api/integrations/photos/{photo.id}/")
    if response.status_code != 200:
        raise AssertionError("Approved person share did not authorize the photo")
    fixtures["person_photo"] = response.json()
    contributor = create_test_user()
    contribution = create_test_photo(
        owner=contributor, captions_json={"user_caption": "Hidden contribution"}
    )
    album.shared_to.add(viewer)
    album.shared_to.add(contributor, through_defaults={"role": "contributor"})
    album.photos.add(contribution, through_defaults={"added_by": contributor})
    for name, path in {
        "contributor_photo": f"/api/integrations/photos/{contribution.id}/",
        "contributor_album": f"/api/integrations/albums/{album.id}/photos/",
    }.items():
        response = client.get(path)
        if response.status_code != 200:
            raise AssertionError((name, response.status_code))
        fixtures[name] = response.json()
    return fixtures
