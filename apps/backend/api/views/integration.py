"""Paged automation reads through existing LibrePhotos search and sharing rules."""

from typing import Any

import requests
from django.db.models import F, Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.accounts.permissions import IsPhotoOrAlbumSharedTo
from api.albums.member_grants import NOTHING, album_grants
from api.drf.exceptions import ServiceUnavailable
from api.drf.pagination import IntegrationPagination, PaginatedViewMixin
from api.drf.params import parse_query
from api.drf.request_user import request_user
from api.models import AlbumUser, AlbumUserPhoto, Face, LongRunningJob, Photo
from api.runtime.remote_inference import RemoteInferenceError
from api.search.filters import SemanticSearchFilter
from api.search.metadata_filter import MetadataFilterQuery
from api.search.profiles import active_profile, text_search_paused
from api.search.remote_embeddings import remote_embeddings
from api.search.semantic import OPENCLIP, calculate_query_embeddings
from api.search.similarity import (
    SimilarityIndexError,
    search_similar_embedding_strict,
    search_similar_image,
)
from api.serializers.integration import (
    IntegrationAlbumPageSerializer,
    IntegrationJobSerializer,
    IntegrationPhotoPageSerializer,
    IntegrationPhotoSerializer,
    IntegrationSearchQuery,
)
from api.serializers.photos import PhotoSummarySerializer, with_photo_summary_relations
from api.sharing.grants import SUMMARY_FIELDS, redact, viewer_grant
from api.views.custom_api_view import ListViewSet
from api.views.photos import PhotoViewSet
from api.views.search import SearchListViewSet


class IntegrationSearchFilter(SemanticSearchFilter):
    def semantic_topk(self, request: Request) -> int:
        choice = parse_query(request, IntegrationSearchQuery)["semantic"]
        saved = request_user(request).semantic_search_topk
        if choice is False:
            return 0
        if choice is True:
            return min(saved or 100, 1000)
        return min(saved, 1000)

    def _semantic_matches(self, request: Request) -> list[str]:
        if parse_query(request, IntegrationSearchQuery)["semantic"] is not True:
            return super()._semantic_matches(request)
        user = request_user(request)
        query = parse_query(request, IntegrationSearchQuery).get("search", "")
        try:
            profile = active_profile(user)
            if text_search_paused(profile):
                raise RemoteInferenceError("The semantic index requires a rebuild.")
            if profile.provider == OPENCLIP:
                embedding, _magnitude = calculate_query_embeddings(query)
            else:
                embedding = remote_embeddings(profile, [query])[0]
            return search_similar_embedding_strict(
                user,
                embedding,
                self.semantic_topk(request),
                profile=profile,
            )
        except (
            requests.RequestException,
            RemoteInferenceError,
            SimilarityIndexError,
            KeyError,
            ValueError,
            TypeError,
        ):
            raise ServiceUnavailable(
                "Semantic search is unavailable. Check its index and inference service.",
                code="semantic_search_unavailable",
            ) from None


class IntegrationSearchView(ListViewSet):
    """Flat pages without materializing or serializing a complete library."""

    permission_classes = (IsAuthenticated,)
    queryset = Photo.objects.none()
    search_fields = SearchListViewSet.search_fields
    pagination_class = IntegrationPagination
    serializer_class = PhotoSummarySerializer
    filter_backends = (IntegrationSearchFilter,)

    @extend_schema(parameters=[IntegrationSearchQuery, MetadataFilterQuery])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        values = parse_query(request, IntegrationSearchQuery)
        photos = with_photo_summary_relations(
            Photo.visible.owned_by(request_user(request))
        ).order_by(F("exif_timestamp").desc(nulls_last=True), "pk")
        if "album_id" in values:
            album = get_object_or_404(
                AlbumUser.objects.owned_or_shared_to(request_user(request)),
                pk=values["album_id"],
            )
            links = AlbumUserPhoto.objects.vouched().filter(albumuser=album)
            photos = photos.filter(pk__in=links.values("photo_id"))
        photos = self.filter_queryset(photos)
        # Structured owner-only filters do not probe hidden share metadata.
        page = self.paginate_queryset(photos)
        return self.get_paginated_response(
            PhotoSummarySerializer(page, many=True, context={"request": request}).data
        )


class IntegrationPhotoView(PhotoViewSet):
    def get_serializer_class(self) -> type[IntegrationPhotoSerializer]:
        return IntegrationPhotoSerializer

    permission_classes = (IsAuthenticated,)
    lookup_url_kwarg = "photo_id"

    def get_permissions(self) -> list[BasePermission]:
        return [IsAuthenticated(), IsPhotoOrAlbumSharedTo()]

    def _with_detail_relations(self, photo: Photo) -> Photo:
        first_faces = Face.objects.filter(photo=photo).order_by("id").values("id")[:100]
        faces = (
            Face.objects.select_related(
                "person", "cluster_person", "classification_person"
            )
            .filter(pk__in=first_faces)
            .order_by("id")
        )
        return (
            Photo.objects.select_related(
                "owner",
                "thumbnail",
                "main_file",
                "caption_instance",
                "search_instance",
                "metadata",
            )
            .prefetch_related(Prefetch("faces", queryset=faces))
            .get(pk=photo.pk)
        )

    def get_object(self) -> Photo:
        self.kwargs["photo_id"] = str(self.kwargs["photo_id"])
        return super().get_object()


class IntegrationSimilarView(PaginatedViewMixin, APIView):
    permission_classes = (IsAuthenticated,)
    pagination_class = IntegrationPagination

    @extend_schema(responses=IntegrationPhotoPageSerializer)
    def get(self, request: Request, photo_id: str) -> Response:
        user = request_user(request)
        photo = get_object_or_404(Photo.visible.owned_by(user), pk=photo_id)
        try:
            hashes = search_similar_image(user, photo, result_count=1000, strict=True)
        except (
            requests.RequestException,
            SimilarityIndexError,
            KeyError,
            ValueError,
            TypeError,
        ):
            raise ServiceUnavailable(
                "Similarity search is unavailable.", code="similarity_unavailable"
            ) from None
        if isinstance(hashes, dict):
            hashes = hashes["result"]
        from django.db.models import Case, IntegerField, When

        rank = Case(
            *[
                When(image_hash=value, then=index)
                for index, value in enumerate(hashes[:1000])
            ],
            default=1000,
            output_field=IntegerField(),
        )
        photos = with_photo_summary_relations(
            Photo.visible.owned_by(user)
            .filter(image_hash__in=hashes[:1000])
            .exclude(pk=photo.pk)
        ).order_by(rank, "pk")
        page = self.paginate_queryset(photos)
        return self.get_paginated_response(
            PhotoSummarySerializer(page, many=True, context={"request": request}).data
        )


class IntegrationAlbumView(PaginatedViewMixin, APIView):
    permission_classes = (IsAuthenticated,)
    pagination_class = IntegrationPagination

    @extend_schema(responses=IntegrationAlbumPageSerializer)
    def get(self, request: Request, album_id: int) -> Response:
        user = request_user(request)
        album = get_object_or_404(
            AlbumUser.objects.owned_or_shared_to(user), pk=album_id
        )
        links = AlbumUserPhoto.objects.vouched().filter(albumuser=album)
        photos = with_photo_summary_relations(
            Photo.visible.filter(pk__in=links.values("photo_id"))
        ).order_by(F("exif_timestamp").desc(nulls_last=True), "pk")
        page = self.paginate_queryset(photos)
        serializer = PhotoSummarySerializer(
            page, many=True, context={"request": request}
        )
        data = serializer.data
        grants = album_grants(user, [photo.id for photo in page or []], album=album)
        for item, photo in zip(data, page or [], strict=True):
            if (
                photo.owner_id != user.pk
                and viewer_grant(serializer, photo.owner_id) is None
            ):
                redact(item, SUMMARY_FIELDS, grants.get(photo.id, NOTHING))
        response = self.get_paginated_response(data)
        response.data["album"] = {"id": album.id, "title": album.title}
        return response


class IntegrationJobView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses=IntegrationJobSerializer)
    def get(self, request: Request, job_id: str) -> Response:
        job = get_object_or_404(
            LongRunningJob.objects.owned_by(request_user(request)), job_id=job_id
        )
        return Response(IntegrationJobSerializer(job).data)
