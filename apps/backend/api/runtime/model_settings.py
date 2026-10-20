"""Database settings for remote providers. Secrets never enter API responses."""

from collections.abc import Mapping

from api.models.remote_model import EmbeddingSpace, PhotoEmbedding, RemoteModelConfig

CONFIG_FIELDS = (
    "disable_thinking",
    "url",
    "model_name",
    "revision",
    "max_num_patches",
    "search_threshold",
    "similar_threshold",
    "tag_threshold",
)


def remote_config(kind: str) -> RemoteModelConfig:
    """The saved settings, or unsaved defaults for a new installation."""
    return RemoteModelConfig.objects.filter(pk=kind).first() or RemoteModelConfig(
        kind=kind
    )


def public_remote_config(kind: str) -> dict[str, object]:
    config = remote_config(kind)
    return {
        **{name: getattr(config, name) for name in CONFIG_FIELDS},
        "has_token": bool(config.token),
    }


def save_remote_config(kind: str, values: Mapping[str, object]) -> None:
    config = remote_config(kind)
    previous_tag_threshold = config.tag_threshold
    for name in CONFIG_FIELDS:
        if name in values:
            setattr(config, name, values[name])
    token = values.get("token")
    if isinstance(token, str) and token.strip():
        config.token = token.strip()
    if values.get("clear_token") is True:
        config.token = ""
    config.save()
    if kind == "embeddings":
        # Token rotation does not change the vector space or require reindexing.
        EmbeddingSpace.objects.filter(
            specification__url=config.url, specification__model_name=config.model_name
        ).update(token=config.token)
        if config.tag_threshold != previous_tag_threshold:
            PhotoEmbedding.objects.filter(
                space__specification__url=config.url,
                space__specification__model_name=config.model_name,
            ).update(tagged=False)
