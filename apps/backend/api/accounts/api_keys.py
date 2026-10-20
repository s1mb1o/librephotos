"""Generate and verify high-entropy API keys without retaining their secrets."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.request import Request

from api.accounts.api_key_policy import DEFAULT_PERMISSIONS, required_permission
from api.models.api_key import APIKey
from api.models.user import User


def create_api_key(
    owner: User,
    name: str,
    permissions: list[str] | None = None,
    expires_at: datetime | None = None,
) -> tuple[APIKey, str]:
    secret = secrets.token_urlsafe(32)
    key = APIKey.objects.create(
        owner=owner,
        name=name,
        permissions=list(DEFAULT_PERMISSIONS) if permissions is None else permissions,
        verifier=hashlib.sha256(secret.encode()).hexdigest(),
        expires_at=expires_at,
    )
    return key, f"lp_{key.id.hex}.{secret}"


class APIKeyAuthentication(BaseAuthentication):
    """Validate every request against the database, then restrict its capability."""

    def authenticate(self, request: Request) -> tuple[User, APIKey] | None:
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b"api-key":
            return None
        if len(parts) != 2 or len(parts[1]) > 128:
            raise AuthenticationFailed("Invalid API key.", code="invalid_api_key")
        try:
            identifier, secret = parts[1].decode("ascii").split(".", 1)
            if not identifier.startswith("lp_") or len(identifier) != 35:
                raise ValueError
            key_id = uuid.UUID(hex=identifier[3:])
        except ValueError, UnicodeError:
            raise AuthenticationFailed(
                "Invalid API key.", code="invalid_api_key"
            ) from None
        key = APIKey.objects.select_related("owner").filter(pk=key_id).first()
        now = timezone.now()
        digest = hashlib.sha256(secret.encode()).hexdigest()
        if (
            key is None
            or not secrets.compare_digest(key.verifier, digest)
            or key.revoked_at is not None
            or not key.owner.is_active
            or key.expires_at is not None
            and key.expires_at <= now
        ):
            raise AuthenticationFailed("Invalid API key.", code="invalid_api_key")
        permission = required_permission(request)
        if permission is None or permission not in key.permissions:
            raise PermissionDenied(
                "This API key does not permit this operation.", code="api_key_scope"
            )
        cutoff = now - timedelta(minutes=1)
        if key.last_used_at is None or key.last_used_at < cutoff:
            APIKey.objects.filter(pk=key.pk).filter(
                Q(last_used_at__isnull=True) | Q(last_used_at__lt=cutoff)
            ).update(last_used_at=now)
        return key.owner, key

    def authenticate_header(self, request: HttpRequest) -> str:
        return "Api-Key"
