"""Stored remote settings, immutable embedding spaces, and cached vectors."""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django_cryptography.fields import encrypt

from api.models.scopes import OwnedQuerySet


class RemoteModelConfig(models.Model):
    """Connection settings editable by administrators. Tokens stay on the server."""

    kind = models.CharField(max_length=16, primary_key=True)
    url = models.CharField(max_length=2048, blank=True, default="")
    model_name = models.CharField(max_length=255, blank=True, default="")
    token = encrypt(models.TextField(blank=True, default=""))
    disable_thinking = models.BooleanField(default=False)
    revision = models.CharField(max_length=255, blank=True, default="unspecified")
    max_num_patches = models.PositiveIntegerField(default=256)
    search_threshold = models.FloatField(default=0.15)
    similar_threshold = models.FloatField(default=0.8)
    tag_threshold = models.FloatField(default=0.25)

    def __str__(self) -> str:
        return self.kind


class EmbeddingSpace(models.Model):
    """The complete vector-producing profile. Its key excludes credentials."""

    key = models.CharField(max_length=64, primary_key=True)
    specification = models.JSONField()
    token = encrypt(models.TextField(blank=True, default=""))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.key


class PhotoEmbeddingQuerySet(OwnedQuerySet["PhotoEmbedding"]):
    owner_lookup: ClassVar[str] = "photo__owner"


class PhotoEmbedding(models.Model):
    """One cached vector and its generated labels for a photo in a space."""

    photo = models.ForeignKey(
        "Photo", on_delete=models.CASCADE, related_name="semantic_embeddings"
    )
    space = models.ForeignKey(EmbeddingSpace, on_delete=models.CASCADE)
    vector = models.JSONField()
    source_hash = models.CharField(max_length=64, default="")
    tags = models.JSONField(default=list)
    tagged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PhotoEmbeddingQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["photo", "space"], name="unique_photo_embedding_space"
            )
        ]

    def __str__(self) -> str:
        return f"{self.photo_id}:{self.space_id}"


class SemanticIndexQuerySet(OwnedQuerySet["SemanticIndex"]):
    pass


class SemanticIndex(models.Model):
    """The successfully built active space. A null space uses legacy OpenCLIP."""

    owner = models.OneToOneField(
        "User",
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="semantic_index",
    )
    space = models.ForeignKey(EmbeddingSpace, null=True, on_delete=models.PROTECT)

    objects = SemanticIndexQuerySet.as_manager()

    def __str__(self) -> str:
        return f"{self.owner_id}:{self.space_id or 'openclip_vitb32'}"
