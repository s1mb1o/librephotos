"""Remote vision captions using the configured OpenAI-compatible provider."""

from api.models.remote_model import RemoteModelConfig
from api.runtime.remote_inference import RemoteInferenceError, image_data_url, post_json


def generate_remote_caption(
    image_path: str,
    prompt: str | None,
    config: RemoteModelConfig | None = None,
) -> str:
    config = config or RemoteModelConfig.objects.filter(pk="captioning").first()
    if config is None or not config.url or not config.model_name:
        raise RemoteInferenceError(
            "Configure the captioning API URL and model name in the admin settings."
        )
    payload: dict[str, object] = {
        "model": config.model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                        or "Describe this image in a short, natural image caption.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url(image_path)},
                    },
                ],
            }
        ],
    }
    if config.disable_thinking:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    body = post_json(config.url, config.token, "/chat/completions", payload)
    choices = body.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            text = message.get("content")
            if isinstance(text, str) and text.strip():
                return text.strip()
    raise RemoteInferenceError(
        "The model provider returned no caption text. Use a model that supports image input."
    )
