"""Revocable user credentials. The complete secret is never stored."""

import uuid

from django.db import models

from api.models.scopes import OwnedQuerySet


class APIKeyQuerySet(OwnedQuerySet["APIKey"]):
    pass


class APIKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey("User", on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=128)
    verifier = models.CharField(max_length=64)
    permissions = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = APIKeyQuerySet.as_manager()

    def __str__(self) -> str:
        return str(self.id)
