"""Permanent credentials remain user-scoped, revocable, and permission-limited."""

import hashlib
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from api.accounts.api_key_policy import PERMISSIONS
from api.accounts.api_keys import create_api_key
from api.models.api_key import APIKey
from api.tests.utils import create_test_job, create_test_photo, create_test_user


class APIKeysTest(TestCase):
    def setUp(self) -> None:
        self.owner = create_test_user()
        self.other = create_test_user()
        self.photo = create_test_photo(owner=self.owner)
        self.private = create_test_photo(owner=self.other)
        self.client = APIClient()
        self.key, self.secret = create_api_key(self.owner, "automation")

    def use_key(self, secret: str | None = None) -> None:
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key {secret or self.secret}")

    def use_account(self) -> None:
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.owner)}"
        )

    def test_read_and_user_isolation(self) -> None:
        self.use_key()
        self.assertEqual(
            self.client.get(f"/api/photos/{self.photo.id}/").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/api/photos/{self.private.id}/").status_code, 404
        )
        self.key.refresh_from_db()
        self.assertIsNotNone(self.key.last_used_at)

    def test_key_secret_is_not_stored(self) -> None:
        secret = self.secret.split(".")[1]
        self.assertEqual(self.key.verifier, hashlib.sha256(secret.encode()).hexdigest())
        self.assertNotIn(secret, repr(self.key.__dict__))
        self.assertNotIn(secret, str(self.key))

    def test_creation_shows_secret_once_and_defaults_to_reads(self) -> None:
        self.use_account()
        response = self.client.post(
            "/api/auth/keys/", {"name": "second"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertTrue(data["key"].startswith("lp_"))
        self.assertIsNone(data["expires_at"])
        self.assertEqual(data["permissions"], ["photos:read", "jobs:read"])
        self.assertEqual(response["Cache-Control"], "no-store")
        listing = self.client.get("/api/auth/keys/")
        self.assertNotIn(data["key"], listing.content.decode())
        self.assertNotIn("verifier", listing.content.decode())
        self.assertEqual(listing.json()["count"], 2)

    def test_key_cannot_manage_keys_or_accounts_even_with_all_scopes(self) -> None:
        APIKey.objects.filter(pk=self.key.pk).update(permissions=list(PERMISSIONS))
        self.use_key()
        for method, url, body in [
            ("get", "/api/auth/keys/", {}),
            ("post", "/api/auth/keys/", {"name": "forbidden"}),
            ("delete", f"/api/auth/keys/{self.key.id}/", {}),
            ("patch", f"/api/user/{self.owner.id}/", {"is_staff": True}),
        ]:
            with self.subTest(method=method, url=url):
                self.assertIn(
                    getattr(self.client, method)(url, body, format="json").status_code,
                    (401, 403),
                )

    def test_read_key_refuses_writes_and_get_job_triggers(self) -> None:
        self.use_key()
        for method, url in [
            ("patch", f"/api/photos/{self.photo.id}/metadata/"),
            ("patch", f"/api/photos/{self.photo.id}/"),
            ("post", "/api/albums/user/edit/"),
            ("post", "/api/scanphotos/"),
            ("get", "/api/scanphotos/"),
            ("get", "/api/sitesettings/"),
        ]:
            with self.subTest(method=method, url=url):
                self.assertEqual(
                    getattr(self.client, method)(url, {}, format="json").status_code,
                    403,
                )

    def test_metadata_permission_does_not_grant_album_or_job_submission(self) -> None:
        APIKey.objects.filter(pk=self.key.pk).update(permissions=["metadata:write"])
        self.use_key()
        # A permitted route reaches its body validator. A missing or foreign photo does not.
        self.assertEqual(
            self.client.patch(
                f"/api/photos/{self.photo.id}/metadata/", {"rating": 3}, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/photos/{self.private.id}/metadata/", {"rating": 3}, format="json"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/api/albums/user/edit/", {}, format="json").status_code,
            403,
        )

    def test_owner_revoke_takes_effect_on_next_request(self) -> None:
        self.use_key()
        self.assertEqual(
            self.client.get(f"/api/photos/{self.photo.id}/").status_code, 200
        )
        self.use_account()
        self.assertEqual(
            self.client.delete(f"/api/auth/keys/{self.key.id}/").status_code, 204
        )
        self.use_key()
        self.assertEqual(
            self.client.get(f"/api/photos/{self.photo.id}/").status_code, 401
        )

    def test_another_account_cannot_list_or_revoke_a_key(self) -> None:
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.other)}"
        )
        self.assertEqual(self.client.get("/api/auth/keys/").json()["count"], 0)
        self.assertEqual(
            self.client.delete(f"/api/auth/keys/{self.key.id}/").status_code, 404
        )

    def test_expired_deactivated_deleted_and_revoked_keys_fail(self) -> None:
        self.use_key()
        now = timezone.now()
        with patch(
            "api.accounts.api_keys.timezone.now", return_value=now + timedelta(days=1)
        ):
            APIKey.objects.filter(pk=self.key.pk).update(expires_at=now)
            self.assertEqual(
                self.client.get(f"/api/photos/{self.photo.id}/").status_code, 401
            )
        APIKey.objects.filter(pk=self.key.pk).update(expires_at=None)
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.assertEqual(
            self.client.get(f"/api/photos/{self.photo.id}/").status_code, 401
        )
        # Cascade deletion removes the verifier without an authentication cache.
        self.key.delete()
        self.assertEqual(
            self.client.get(f"/api/photos/{self.photo.id}/").status_code, 401
        )

    def test_invalid_keys_fail_without_echoing_credentials(self) -> None:
        for secret in [
            "garbage",
            self.secret + "tampered",
            f"lp_{uuid.uuid4().hex}.unknown",
            "x y",
        ]:
            self.use_key(secret)
            response = self.client.get(f"/api/photos/{self.photo.id}/")
            self.assertEqual(response.status_code, 401)
            self.assertNotIn(secret, response.content.decode())

    def test_keys_in_query_parameters_are_not_accepted(self) -> None:
        response = self.client.get(
            f"/api/photos/{self.photo.id}/", {"api_key": self.secret}
        )
        self.assertEqual(response.status_code, 404)
        self.key.refresh_from_db()
        self.assertIsNone(self.key.last_used_at)

    def test_validation_and_expiration(self) -> None:
        self.use_account()
        for values in [
            {"name": ""},
            {"name": "test", "permissions": ["admin"]},
            {"name": "test", "permissions": []},
            {"name": "test", "expires_at": "2000-01-01T00:00:00Z"},
        ]:
            self.assertEqual(
                self.client.post("/api/auth/keys/", values, format="json").status_code,
                400,
            )
        future = (timezone.now() + timedelta(days=1)).isoformat()
        self.assertEqual(
            self.client.post(
                "/api/auth/keys/",
                {"name": "temporary", "expires_at": future},
                format="json",
            ).status_code,
            201,
        )

    def test_media_route_authenticates_key_before_cookie_fallback(self) -> None:
        self.use_key()
        response = self.client.get(f"/media/thumbnails_big/{self.private.image_hash}")
        self.assertNotEqual(response.status_code, 200)
        APIKey.objects.filter(pk=self.key.pk).update(permissions=["jobs:read"])
        self.assertEqual(
            self.client.get(
                f"/media/thumbnails_big/{self.photo.image_hash}"
            ).status_code,
            403,
        )

    def test_jwt_still_authenticates(self) -> None:
        self.use_account()
        self.assertEqual(
            self.client.get(f"/api/photos/{self.photo.id}/").status_code, 200
        )

    def test_staff_key_cannot_read_other_users_jobs_or_metadata(self) -> None:
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        own = create_test_job(started_by=self.owner)
        other = create_test_job(started_by=self.other)
        self.use_key()
        listing = self.client.get("/api/jobs/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(
            [row["job_id"] for row in listing.json()["results"]], [own.job_id]
        )
        self.assertEqual(self.client.get(f"/api/jobs/{other.pk}/").status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/photos/{self.private.id}/metadata/").status_code, 404
        )
        APIKey.objects.filter(pk=self.key.pk).update(permissions=list(PERMISSIONS))
        self.assertEqual(
            self.client.post(f"/api/manage/user/{self.other.id}/scan/").status_code, 403
        )

    def test_album_write_and_job_submission_scopes_are_independent(self) -> None:
        APIKey.objects.filter(pk=self.key.pk).update(permissions=["albums:write"])
        self.use_key()
        response = self.client.post(
            "/api/albums/user/edit/",
            {"title": "API album", "photos": []},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.client.get("/api/jobs/").status_code, 403)
        APIKey.objects.filter(pk=self.key.pk).update(permissions=["jobs:submit"])
        with (
            patch("api.views.scan_triggers._validate_scan_directory"),
            patch(
                "api.views.scan_triggers._start_photo_scan",
                return_value=Response({"job_id": str(uuid.uuid4())}),
            ) as start,
        ):
            self.assertEqual(self.client.post("/api/scanphotos/").status_code, 200)
            start.assert_called_once_with(self.owner, self.owner.scan_directory)

    def test_deleted_account_invalidates_its_key(self) -> None:
        user = create_test_user()
        key, secret = create_api_key(user, "deleted account")
        user.delete()
        self.assertFalse(APIKey.objects.filter(pk=key.pk).exists())
        self.use_key(secret)
        self.assertEqual(self.client.get("/api/jobs/").status_code, 401)

    def test_invalid_key_does_not_fall_back_to_valid_cookie(self) -> None:
        self.client.cookies["jwt"] = str(AccessToken.for_user(self.owner))
        self.use_key(self.secret + "invalid")
        self.assertEqual(
            self.client.get(
                f"/media/thumbnails_big/{self.photo.image_hash}"
            ).status_code,
            401,
        )
        APIKey.objects.filter(pk=self.key.pk).update(permissions=["jobs:read"])
        self.use_key()
        self.assertEqual(
            self.client.get(
                f"/media/thumbnails_big/{self.photo.image_hash}"
            ).status_code,
            403,
        )

    def test_every_policy_view_is_routed(self) -> None:
        from api.accounts.api_key_policy import READ_VIEWS, WRITES
        from api.tests.infra.routes import api_routes

        routed = {
            f"{route.view.__module__.removeprefix('api.views.')}.{route.view.__name__}"
            for route in api_routes()
        }
        from django.urls import resolve

        media_view = resolve("/media/thumbnails_big/abcdef").func.cls
        routed.add(f"media.{media_view.__name__}")
        self.assertFalse(READ_VIEWS - routed)
        self.assertFalse({view for view, method in WRITES} - routed)

    def test_read_key_search_and_media_succeed_with_staff_isolation(self) -> None:
        from api.tests.utils import create_test_album_user

        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        self.use_key()
        self.assertEqual(self.client.get("/api/photos/searchlist/").status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/photos/{self.photo.id}/").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/api/photos/{self.private.id}/").status_code, 404
        )
        self.assertEqual(
            self.client.get(
                f"/media/thumbnails_big/{self.photo.image_hash}"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                f"/media/thumbnails_big/{self.private.image_hash}"
            ).status_code,
            404,
        )
        album = create_test_album_user(owner=self.other)
        self.assertEqual(
            self.client.get(f"/api/albums/user/{album.id}/").status_code, 404
        )

    def test_policy_views_accept_api_key_authentication(self) -> None:
        from django.urls import resolve

        from api.accounts.api_key_policy import READ_VIEWS, WRITES
        from api.accounts.api_keys import APIKeyAuthentication
        from api.tests.infra.routes import api_routes

        classes = {route.view for route in api_routes()}
        classes.add(resolve("/media/thumbnails_big/abcdef").func.cls)
        identities = READ_VIEWS | {view for view, method in WRITES}
        for view in classes:
            identity = f"{view.__module__.removeprefix('api.views.')}.{view.__name__}"
            if identity in identities:
                self.assertIn(APIKeyAuthentication, view.authentication_classes)

    def test_last_used_writes_are_limited_and_revocation_time_is_retained(self) -> None:
        self.use_key()
        self.client.get("/api/jobs/")
        self.key.refresh_from_db()
        first = self.key.last_used_at
        self.client.get("/api/jobs/")
        self.key.refresh_from_db()
        self.assertEqual(self.key.last_used_at, first)
        self.use_account()
        self.client.delete(f"/api/auth/keys/{self.key.id}/")
        self.key.refresh_from_db()
        revoked = self.key.revoked_at
        self.client.delete(f"/api/auth/keys/{self.key.id}/")
        self.key.refresh_from_db()
        self.assertEqual(self.key.revoked_at, revoked)

    def test_expired_keys_do_not_use_active_key_limit(self) -> None:
        for index in range(99):
            create_api_key(
                self.owner,
                f"expired-{index}",
                expires_at=timezone.now() - timedelta(days=1),
            )
        self.use_account()
        self.assertEqual(
            self.client.post(
                "/api/auth/keys/", {"name": "replacement"}, format="json"
            ).status_code,
            201,
        )

    def test_jwt_challenge_is_preserved(self) -> None:
        response = self.client.get("/api/jobs/")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response["WWW-Authenticate"].startswith("Bearer"))

    def test_upload_rejects_api_key_even_with_a_valid_cookie(self) -> None:
        from django.test import RequestFactory

        from api.views.upload import authenticate_upload_request
        from chunked_upload.exceptions import ChunkedUploadError

        request = RequestFactory().post(
            "/api/upload/", HTTP_AUTHORIZATION=f"Api-Key {self.secret}"
        )
        request.COOKIES["jwt"] = str(AccessToken.for_user(self.owner))
        with self.assertRaises(ChunkedUploadError):
            authenticate_upload_request(request)
