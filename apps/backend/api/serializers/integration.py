"""Bounded REST representations for automation clients."""

from typing import TypedDict

from rest_framework import serializers

from api.drf.request_user import request_user
from api.models import AlbumUser, AlbumUserPhoto, LongRunningJob, Photo
from api.serializers.photos import PhotoSerializer


class IntegrationSearchQuery(serializers.Serializer[None]):
    search = serializers.CharField(required=False, allow_blank=True, max_length=512)
    semantic = serializers.BooleanField(required=False, allow_null=True, default=None)
    album_id = serializers.IntegerField(required=False, min_value=1)


class AlbumReference(TypedDict):
    id: int
    title: str


PHOTO_DETAIL_FIELDS = (
    "id",
    "image_hash",
    "exif_timestamp",
    "caption",
    "people",
    "rating",
    "width",
    "height",
    "video",
    "square_thumbnail_url",
)


class IntegrationPersonSerializer(serializers.Serializer[None]):
    name = serializers.CharField(read_only=True)
    face_id = serializers.IntegerField(allow_null=True, read_only=True)


class IntegrationPhotoSerializer(serializers.ModelSerializer):
    """Compose the existing sharing-aware serializer with an explicit field allowlist."""

    caption = serializers.CharField(allow_null=True, read_only=True)
    people = IntegrationPersonSerializer(many=True, allow_null=True, read_only=True)
    width = serializers.IntegerField(allow_null=True, read_only=True)
    height = serializers.IntegerField(allow_null=True, read_only=True)
    square_thumbnail_url = serializers.CharField(read_only=True)
    album_refs = serializers.SerializerMethodField(allow_null=True)

    class Meta:
        model = Photo
        fields = (*PHOTO_DETAIL_FIELDS, "album_refs")
        read_only_fields = fields

    def get_album_refs(self, obj: Photo) -> list[AlbumReference] | None:
        user = request_user(self.context["request"])
        if obj.owner_id != user.pk:
            return None
        links = AlbumUserPhoto.objects.vouched().filter(photo=obj)
        albums = AlbumUser.objects.owned_or_shared_to(user).filter(
            pk__in=links.values("albumuser_id")
        )
        return [
            {"id": album_id, "title": title}
            for album_id, title in albums.order_by("id").values_list("id", "title")[
                :100
            ]
        ]

    def to_representation(self, instance: Photo) -> dict[str, object]:
        source = PhotoSerializer(instance, context=self.context)
        for name in list(source.fields):
            if name not in PHOTO_DETAIL_FIELDS and name != "captions_json":
                source.fields.pop(name)
        represented = source.data
        data: dict[str, object] = {
            name: represented.get(name)
            for name in PHOTO_DETAIL_FIELDS
            if name != "caption"
        }
        captions: object = represented.get("captions_json")
        caption: object = None
        if isinstance(captions, dict):
            caption = captions.get("user_caption") or captions.get("im2txt", "")
        data["caption"] = caption[:16384] if isinstance(caption, str) else None
        people = data.get("people")
        if isinstance(people, list):
            data["people"] = [
                {"name": entry.get("name", ""), "face_id": entry.get("face_id")}
                for entry in people[:100]
                if isinstance(entry, dict)
            ]
        data["album_refs"] = self.get_album_refs(instance)
        return data


class IntegrationJobResult(TypedDict):
    errors: list[str]
    error_count: int


class IntegrationJobSerializer(serializers.ModelSerializer):
    result = serializers.SerializerMethodField()

    def get_result(self, obj: LongRunningJob) -> IntegrationJobResult:
        raw: object = obj.result
        errors: list[str] = []
        count = 0
        if isinstance(raw, dict):
            values = raw.get("errors", [])
            if isinstance(values, list):
                count = len(values)
                for item in values[:100]:
                    value: object = item
                    if isinstance(item, dict):
                        value = item.get("message", item.get("error"))
                    if isinstance(value, str):
                        errors.append(value[:512])
            if not errors and isinstance(raw.get("error"), str):
                errors.append(raw["error"][:512])
                count = max(1, count)
        return {"errors": errors, "error_count": count}

    class Meta:
        model = LongRunningJob
        fields = (
            "job_id",
            "finished",
            "failed",
            "cancelled",
            "progress_current",
            "progress_target",
            "progress_step",
            "started_at",
            "finished_at",
            "result",
        )
        read_only_fields = fields


class IntegrationAlbumReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlbumUser
        fields = ("id", "title")
        read_only_fields = fields


class IntegrationPhotoPageSerializer(serializers.Serializer[None]):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    num_pages = serializers.IntegerField()
    from api.serializers.photos import PhotoSummarySerializer

    results = PhotoSummarySerializer(many=True)


class IntegrationAlbumPageSerializer(IntegrationPhotoPageSerializer):
    album = IntegrationAlbumReferenceSerializer()
