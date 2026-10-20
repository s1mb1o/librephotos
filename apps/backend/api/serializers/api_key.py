"""Account-key metadata and one-time creation response."""

from datetime import datetime

from django.utils import timezone
from rest_framework import serializers

from api.accounts.api_key_policy import DEFAULT_PERMISSIONS, PERMISSIONS
from api.models.api_key import APIKey


class APIKeySerializer(serializers.ModelSerializer):
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=PERMISSIONS), read_only=True
    )

    class Meta:
        model = APIKey
        fields: tuple[str, ...] = (
            "id",
            "name",
            "permissions",
            "created_at",
            "expires_at",
            "last_used_at",
            "revoked_at",
        )
        read_only_fields: tuple[str, ...] = fields


class APIKeyCreatedSerializer(APIKeySerializer):
    key = serializers.CharField(
        read_only=True, help_text="Complete secret. Shown only in this response."
    )

    class Meta(APIKeySerializer.Meta):
        fields = (*APIKeySerializer.Meta.fields, "key")
        read_only_fields = fields


class APIKeyCreateRequest(serializers.Serializer[None]):
    name = serializers.CharField(max_length=128)
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=PERMISSIONS),
        default=list(DEFAULT_PERMISSIONS),
        allow_empty=False,
        max_length=len(PERMISSIONS),
    )
    expires_at = serializers.DateTimeField(
        required=False, allow_null=True, default=None
    )

    def validate_expires_at(self, value: datetime | None) -> datetime | None:
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("Expiration must be in the future.")
        return value

    def validate_permissions(self, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))
