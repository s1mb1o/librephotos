"""Bounded OpenAI-compatible HTTP calls. Never expose provider credentials."""

import base64
import io
import json
from urllib.parse import urlsplit

import PIL.Image
import requests


class RemoteInferenceError(RuntimeError):
    """A remote provider could not produce a valid result."""


def validate_base_url(value: str) -> str:
    """Normalize an HTTP base URL without embedded credentials or query data."""
    value = value.strip().rstrip("/")
    try:
        parts = urlsplit(value)
        valid = parts.scheme in {"http", "https"} and parts.hostname and parts.port != 0
    except ValueError:
        valid = False
        parts = urlsplit("")
    if not valid or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError(
            "Use an HTTP or HTTPS API base URL without credentials, query parameters, or a fragment."
        )
    return value


def image_data_url(path: str) -> str:
    """A metadata-free JPEG with the thumbnail's native aspect ratio."""
    try:
        with PIL.Image.open(path) as image:
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=90)
    except OSError, ValueError:
        raise RemoteInferenceError("The photo thumbnail could not be read.") from None
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode(
        "ascii"
    )


def post_json(
    url: str, token: str, endpoint: str, body: dict[str, object]
) -> dict[str, object]:
    """Return a JSON object. Error messages contain neither URLs nor response data."""
    try:
        base = validate_base_url(url)
    except ValueError:
        raise RemoteInferenceError(
            "Configure a valid API base URL in the admin settings."
        ) from None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        response = requests.post(
            base + endpoint,
            data=json.dumps(body),
            headers=headers,
            timeout=(10, 180),
            allow_redirects=False,
        )
    except requests.Timeout:
        raise RemoteInferenceError(
            "The model request timed out. Check provider availability and model load time."
        ) from None
    except requests.RequestException:
        raise RemoteInferenceError(
            "Cannot connect to the model provider. Check its URL and network access."
        ) from None
    if not 200 <= response.status_code < 300:
        raise RemoteInferenceError(
            f"Model provider returned HTTP {response.status_code}. Check the API URL, access token, model name, and image support."
        )
    try:
        data: object = response.json()
    except ValueError:
        raise RemoteInferenceError(
            "The model provider returned invalid JSON."
        ) from None
    if not isinstance(data, dict):
        raise RemoteInferenceError(
            "The model provider returned an invalid response object."
        )
    return {str(key): value for key, value in data.items()}
