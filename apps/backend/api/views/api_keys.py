"""API-key management requires an account credential, never an API key."""

from django.db.models import QuerySet
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from api.accounts.api_keys import create_api_key
from api.accounts.authentication import ThrottledBasicAuthentication
from api.drf.params import parse_body
from api.drf.request_user import request_user
from api.models.api_key import APIKey
from api.serializers.api_key import (
    APIKeyCreatedSerializer,
    APIKeyCreateRequest,
    APIKeySerializer,
)


class APIKeyViewSet(
    mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    authentication_classes = (JWTAuthentication, ThrottledBasicAuthentication)
    permission_classes = (IsAuthenticated,)
    serializer_class = APIKeySerializer

    def get_queryset(self) -> QuerySet[APIKey]:
        if getattr(self, "swagger_fake_view", False):
            return APIKey.objects.none()
        return APIKey.objects.owned_by(request_user(self.request)).order_by(
            "-created_at", "id"
        )

    @extend_schema(
        request=APIKeyCreateRequest, responses={201: APIKeyCreatedSerializer}
    )
    def create(self, request: Request) -> Response:
        values = parse_body(request, APIKeyCreateRequest)
        owner = request_user(request)
        if (
            APIKey.objects.owned_by(owner).filter(revoked_at__isnull=True).count()
            >= 100
        ):
            raise ValidationError(
                "Revoke an existing key before creating another.", code="api_key_limit"
            )
        key, secret = create_api_key(owner, **values)
        data = dict(APIKeySerializer(key).data)
        data["key"] = secret
        response = Response(data, status=status.HTTP_201_CREATED)
        response["Cache-Control"] = "no-store"
        return response

    def perform_destroy(self, instance: APIKey) -> None:
        APIKey.objects.filter(pk=instance.pk).update(revoked_at=timezone.now())
