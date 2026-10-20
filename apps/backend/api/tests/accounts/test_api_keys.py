"""Permanent credentials remain user-scoped, revocable, and permission-limited."""

import hashlib
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from api.accounts.api_key_policy import PERMISSIONS
from api.accounts.api_keys import create_api_key
from api.models.api_key import APIKey
from api.tests.utils import create_test_photo, create_test_user


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
                self.assertIn(
                    getattr(self.client, method)(url, {}, format="json").status_code,
                    (403, 404),
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
