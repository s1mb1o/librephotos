"""Automation endpoints page before serialization and preserve user boundaries."""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.accounts.api_keys import create_api_key
from api.tests.utils import (
    create_test_album_user,
    create_test_job,
    create_test_photo,
    create_test_user,
)


class IntegrationReadsTest(TestCase):
    def setUp(self) -> None:
        self.owner = create_test_user()
        self.other = create_test_user()
        self.client = APIClient()
        _, secret = create_api_key(self.owner, "MCP")
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {secret}")
        self.own = create_test_photo(owner=self.owner, exif_timestamp=timezone.now())
        self.foreign = create_test_photo(
            owner=self.other, exif_timestamp=timezone.now()
        )

    def test_search_is_paged_and_user_scoped(self) -> None:
        for index in range(27):
            create_test_photo(owner=self.owner, exif_timestamp=timezone.now())
        response = self.client.get("/api/integrations/search/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["count"], 28)
        self.assertEqual(len(data["results"]), 25)
        self.assertNotIn(
            str(self.foreign.pk), [photo["id"] for photo in data["results"]]
        )
        self.assertEqual(
            len(self.client.get("/api/integrations/search/?page=2").json()["results"]),
            3,
        )

    def test_page_size_is_bounded_and_bad_input_is_400(self) -> None:
        self.assertEqual(
            self.client.get("/api/integrations/search/?page_size=5000").json()[
                "page_size"
            ],
            100,
        )
        for query in [
            "page=no",
            "semantic=maybe",
            "search=" + "x" * 513,
            "album_id=wrong",
        ]:
            self.assertEqual(
                self.client.get("/api/integrations/search/?" + query).status_code, 400
            )

    def test_semantic_search_keeps_relevance_order(self) -> None:
        second = create_test_photo(owner=self.owner, exif_timestamp=timezone.now())
        with (
            patch(
                "api.views.integration.search_similar_embedding_strict",
                return_value=[self.own.image_hash, second.image_hash],
            ) as semantic,
            patch(
                "api.views.integration.calculate_query_embeddings",
                return_value=([0.0] * 512, 1.0),
            ),
        ):
            response = self.client.get(
                "/api/integrations/search/?search=beach&semantic=true"
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            [photo["id"] for photo in response.json()["results"]],
            [str(self.own.id), str(second.id)],
        )
        semantic.assert_called_once()

    def test_explicit_metadata_search_does_not_call_semantic_service(self) -> None:
        self.owner.semantic_search_topk = 100
        self.owner.save(update_fields=["semantic_search_topk"])
        with patch(
            "api.search.filters.SemanticSearchFilter._semantic_matches"
        ) as semantic:
            self.client.get("/api/integrations/search/?search=beach&semantic=false")
        semantic.assert_not_called()

    def test_photo_detail_has_no_file_paths_and_foreign_photo_is_hidden(self) -> None:
        response = self.client.get(f"/api/integrations/photos/{self.own.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn("image_path", response.json())
        self.assertNotIn("file_variants", response.json())
        self.assertEqual(
            self.client.get(f"/api/integrations/photos/{self.foreign.pk}/").status_code,
            404,
        )

    def test_similarity_is_bounded_user_scoped_and_ordered(self) -> None:
        second = create_test_photo(owner=self.owner, exif_timestamp=timezone.now())
        with patch(
            "api.views.integration.search_similar_image",
            return_value={
                "status": True,
                "result": [
                    second.image_hash,
                    self.foreign.image_hash,
                    self.own.image_hash,
                ],
            },
        ) as similar:
            response = self.client.get(
                f"/api/integrations/photos/{self.own.id}/similar/"
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            [photo["id"] for photo in response.json()["results"]],
            [str(second.id)],
        )
        similar.assert_called_once_with(
            self.owner, self.own, result_count=1000, strict=True
        )
        self.assertEqual(
            self.client.get(
                f"/api/integrations/photos/{self.foreign.id}/similar/"
            ).status_code,
            404,
        )

    def test_album_photos_are_paged_and_private_albums_are_hidden(self) -> None:
        album = create_test_album_user(owner=self.owner)
        album.photos.add(self.own, self.foreign)
        response = self.client.get(f"/api/integrations/albums/{album.id}/photos/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["album"]["id"], album.id)
        self.assertEqual(
            [photo["id"] for photo in response.json()["results"]], [str(self.own.id)]
        )
        private_album = create_test_album_user(owner=self.other)
        self.assertEqual(
            self.client.get(
                f"/api/integrations/albums/{private_album.id}/photos/"
            ).status_code,
            404,
        )

    def test_job_id_lookup_is_owner_scoped_for_admin_keys_too(self) -> None:
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        own = create_test_job(started_by=self.owner)
        foreign = create_test_job(started_by=self.other)
        self.assertEqual(
            self.client.get(f"/api/integrations/jobs/{own.job_id}/").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/api/integrations/jobs/{foreign.job_id}/").status_code,
            404,
        )

    def test_album_filter_does_not_accept_another_users_album(self) -> None:
        private_album = create_test_album_user(owner=self.other)
        self.assertEqual(
            self.client.get(
                f"/api/integrations/search/?album_id={private_album.id}"
            ).status_code,
            404,
        )

    def test_date_camera_rating_and_file_type_filters(self) -> None:
        from datetime import UTC, datetime

        from api.models import File

        wanted = create_test_photo(
            owner=self.owner,
            exif_timestamp=datetime(2020, 5, 3, tzinfo=UTC),
            camera="Wanted Camera",
            rating=5,
        )
        other = create_test_photo(
            owner=self.owner,
            exif_timestamp=datetime(2010, 5, 3, tzinfo=UTC),
            camera="Other Camera",
            rating=1,
        )
        if wanted.main_file is None:
            raise AssertionError("Missing test file")
        wanted.main_file.type = File.VIDEO
        wanted.main_file.save(update_fields=["type"])
        for query in [
            "taken_after=2019-01-01",
            "taken_before=2021-01-01&taken_after=2019-01-01",
            "camera=Wanted%20Camera",
            "rating_min=5",
            "file_type=video",
        ]:
            response = self.client.get(
                "/api/integrations/search/?semantic=false&" + query
            )
            self.assertEqual(response.status_code, 200, response.content)
            ids = [row["id"] for row in response.json()["results"]]
            self.assertIn(str(wanted.id), ids)
            self.assertNotIn(str(other.id), ids)

    def test_person_filter_applies_and_rejects_foreign_people(self) -> None:
        from api.tests.utils import create_test_face, create_test_person

        person = create_test_person(cluster_owner=self.owner)
        create_test_face(photo=self.own, person=person)
        foreign_person = create_test_person(cluster_owner=self.other)
        response = self.client.get(
            f"/api/integrations/search/?semantic=false&person={person.id}"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            [row["id"] for row in response.json()["results"]], [str(self.own.id)]
        )
        self.assertEqual(
            self.client.get(
                f"/api/integrations/search/?person={foreign_person.id}"
            ).status_code,
            400,
        )

    def test_real_backend_contracts_and_caption_privacy(self) -> None:
        import json

        from api.tests.search.mcp_contracts import collect_mcp_contracts

        contracts = collect_mcp_contracts()
        self.assertEqual(contracts["metadata_write"], 200)
        self.assertEqual(contracts["album_add"], 200)
        photo = contracts["photo"]
        self.assertIsInstance(photo, dict)
        self.assertEqual(photo["caption"], "A blue square")
        self.assertNotIn("/volume1/", json.dumps(photo))
        shared = contracts["shared_photo_caption"]
        self.assertEqual(shared["caption"], "A blue square")
        self.assertNotIn("Private Person", json.dumps(shared))
        self.assertNotIn("Private Camera", json.dumps(shared))
        self.assertIn(contracts["shared_photo_hidden"]["caption"], (None, ""))

    def test_shared_album_redacts_disabled_fields(self) -> None:
        from api.tests.utils import create_test_face, create_test_person

        person = create_test_person(cluster_owner=self.other, name="Secret Person")
        self.foreign = create_test_photo(
            owner=self.other, search_location="Secret Location"
        )
        create_test_face(photo=self.foreign, person=person)
        album = create_test_album_user(
            owner=self.other,
            members_share_faces=False,
            members_share_captions=False,
            members_share_location=False,
        )
        album.photos.add(self.foreign)
        album.shared_to.add(self.owner)
        response = self.client.get(f"/api/integrations/photos/{self.foreign.id}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn("Secret Person", response.content.decode())
        self.assertIn(response.json()["caption"], (None, ""))
        page = self.client.get(f"/api/integrations/albums/{album.id}/photos/")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()["results"][0]["id"], str(self.foreign.id))
        self.assertEqual(
            page.json()["results"][0]["image_hash"], self.foreign.image_hash
        )
        self.assertEqual(page.json()["results"][0]["location"], "")

    def test_person_share_preserves_caption_and_name_privacy(self) -> None:
        from api.tests.utils import (
            create_test_face,
            create_test_person,
            create_test_person_share,
            create_test_person_share_photo,
        )

        person = create_test_person(cluster_owner=self.other, name="Private Person")
        create_test_face(photo=self.foreign, person=person)
        create_test_person_share(person, self.owner)
        create_test_person_share_photo(person, self.foreign)
        response = self.client.get(f"/api/integrations/photos/{self.foreign.id}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(response.json()["caption"], (None, ""))
        self.assertNotIn("image_path", response.json())

    def test_contributor_album_uses_both_sides_sharing_ceiling(self) -> None:
        from rest_framework_simplejwt.tokens import AccessToken

        from api.tests.utils import create_test_face, create_test_person

        contributor = create_test_user()
        photo = create_test_photo(
            owner=contributor,
            captions_json={"user_caption": "Private contributor caption"},
        )
        person = create_test_person(
            cluster_owner=contributor, name="Private Contributor Person"
        )
        create_test_face(photo=photo, person=person)
        album = create_test_album_user(
            owner=self.other, members_share_faces=False, members_share_captions=False
        )
        account = APIClient()
        account.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.other)}"
        )
        for user, role in [(contributor, "contributor"), (self.owner, "viewer")]:
            result = account.post(
                "/api/useralbum/share/",
                {
                    "shared": True,
                    "target_user_id": user.id,
                    "album_id": album.id,
                    "role": role,
                },
                format="json",
            )
            self.assertEqual(result.status_code, 200, result.content)
        account.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(contributor)}"
        )
        result = account.post(
            f"/api/albums/user/{album.id}/photos/add/",
            {"photos": [str(photo.id)]},
            format="json",
        )
        self.assertEqual(result.status_code, 200, result.content)
        result = self.client.get(f"/api/integrations/photos/{photo.id}/")
        self.assertEqual(result.status_code, 200, result.content)
        self.assertNotIn("Private contributor caption", result.content.decode())
        self.assertNotIn("Private Contributor Person", result.content.decode())
        page = self.client.get(f"/api/integrations/albums/{album.id}/photos/")
        self.assertEqual(page.status_code, 200, page.content)
        self.assertEqual([row["id"] for row in page.json()["results"]], [str(photo.id)])

    def test_explicit_semantic_failure_is_not_a_metadata_success(self) -> None:
        import requests

        with patch(
            "api.views.integration.calculate_query_embeddings",
            side_effect=requests.Timeout(),
        ):
            response = self.client.get(
                "/api/integrations/search/?search=test&semantic=true"
            )
        self.assertEqual(response.status_code, 503)
        with patch(
            "api.views.integration.search_similar_image", side_effect=requests.Timeout()
        ):
            response = self.client.get(
                f"/api/integrations/photos/{self.own.id}/similar/"
            )
        self.assertEqual(response.status_code, 503)

    def test_bare_md5_exists_lookup_applies_owner_suffix_and_scope(self) -> None:
        digest = self.own.image_hash[:32]
        response = self.client.get(f"/api/exists/{digest}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"exists": True, "photo_id": str(self.own.id)}
        )
        self.assertEqual(
            self.client.get(f"/api/exists/{self.foreign.image_hash[:32]}/").json(),
            {"exists": False, "photo_id": None},
        )
