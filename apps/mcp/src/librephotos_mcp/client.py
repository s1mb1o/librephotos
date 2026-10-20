"""Bounded, authenticated REST and media requests with redacted failures."""

import asyncio
import json
from collections.abc import Mapping, Sequence
from urllib.parse import unquote, urlsplit
from uuid import UUID

import httpx
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ValidationError

type QueryPrimitive = str | int | float | bool | None
type QueryValues = Mapping[str, QueryPrimitive | Sequence[QueryPrimitive]]

MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_PREVIEW_BYTES = 2 * 1024 * 1024


class LibrePhotosError(ToolError):
    pass


class LibrePhotosClient:
    def __init__(
        self, base_url: str, api_key: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Api-Key {api_key}", "Accept-Encoding": "identity"},
            timeout=30,
            follow_redirects=False,
            transport=transport,
            trust_env=False,
        )

    async def __aenter__(self) -> "LibrePhotosClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.http.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: QueryValues | None = None,
        body: Mapping[str, object] | None = None,
        media: bool = False,
        read_body: bool = True,
    ) -> tuple[bytes, str]:
        try:
            async with asyncio.timeout(45):
                async with self.http.stream(method, path, params=params, json=body) as response:
                    if response.status_code in (401, 403):
                        raise LibrePhotosError("LibrePhotos refused this credential or permission.")
                    if response.status_code == 404:
                        raise LibrePhotosError("The requested object is unavailable to this user.")
                    if response.status_code >= 500 and method != "GET":
                        raise LibrePhotosError(
                            "The LibrePhotos write outcome is unknown. Check Jobs or the library before retrying."
                        )
                    if response.status_code == 400:
                        raise LibrePhotosError(
                            "LibrePhotos rejected the input. Check identifiers, filters, and permissions."
                        )
                    if response.status_code == 503:
                        raise LibrePhotosError(
                            "The LibrePhotos service is temporarily unavailable. Check its service and index status."
                        )
                    if response.status_code >= 300:
                        raise LibrePhotosError("LibrePhotos could not complete the request.")
                    if not read_body:
                        return b"", response.headers.get("content-type", "")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        if method != "GET":
                            raise LibrePhotosError(
                                "The LibrePhotos write outcome is unknown. Check Jobs before retrying."
                            )
                        raise LibrePhotosError(
                            "LibrePhotos returned an unsupported response encoding."
                        )
                    data = bytearray()
                    maximum = MAX_PREVIEW_BYTES if media else MAX_JSON_BYTES
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        data.extend(chunk)
                        if len(data) > maximum:
                            if method != "GET":
                                raise LibrePhotosError(
                                    "The LibrePhotos write outcome is unknown. Check Jobs before retrying."
                                )
                            raise LibrePhotosError("LibrePhotos response exceeded the size limit.")
                    return bytes(data), response.headers.get("content-type", "").split(";")[0]
        except (httpx.HTTPError, TimeoutError):
            message = "LibrePhotos request timed out or the service is unavailable."
            if method != "GET":
                message = "The LibrePhotos write outcome is unknown. Check Jobs or the library before retrying."
            raise LibrePhotosError(message) from None

    async def json[T: BaseModel](
        self,
        model: type[T],
        path: str,
        *,
        params: QueryValues | None = None,
        method: str = "GET",
        body: Mapping[str, object] | None = None,
    ) -> T:
        data, _ = await self._request(method, path, params=params, body=body)
        try:
            return model.model_validate_json(data)
        except (ValidationError, ValueError):
            raise LibrePhotosError("LibrePhotos returned an invalid response.") from None

    async def job(self, path: str, body: Mapping[str, object] | None = None) -> dict[str, object]:
        data, _ = await self._request("POST", path, body=body)
        try:
            raw: object = json.loads(data)
        except ValueError:
            raise LibrePhotosError(
                "LibrePhotos accepted the request but its job outcome is unknown. Check Jobs before retrying."
            ) from None
        if isinstance(raw, dict):
            job_id: object = raw.get("job_id")
            # Existing queued-job responses may nest the job metadata.
            job: object = raw.get("job")
            if job_id is None and isinstance(job, dict):
                job_id = job.get("job_id")
            if isinstance(job_id, str):
                try:
                    return {"job_id": str(UUID(job_id))}
                except ValueError:
                    pass
        raise LibrePhotosError(
            "LibrePhotos accepted the request but returned no usable job identifier. Check Jobs before retrying."
        )

    async def change(self, path: str, body: Mapping[str, object]) -> None:
        await self._request("PATCH", path, body=body, read_body=False)

    async def preview(self, url: str) -> tuple[bytes, str]:
        target = httpx.URL(url)
        base = httpx.URL(self.base_url)
        if target.is_absolute_url and (target.scheme, target.host, target.port) != (
            base.scheme,
            base.host,
            base.port,
        ):
            raise LibrePhotosError("LibrePhotos returned an invalid preview URL.")
        parts = urlsplit(url)
        if parts.netloc and not parts.scheme:
            raise LibrePhotosError("LibrePhotos returned an invalid preview URL.")
        path = unquote(parts.path)
        if (
            not path.startswith("/media/")
            or ".." in path.split("/")
            or "\\" in path
            or "%" in path
            or "?" in path
            or "#" in path
            or "\x00" in path
            or parts.query
            or parts.fragment
        ):
            raise LibrePhotosError("LibrePhotos returned an invalid preview URL.")
        data, mime = await self._request("GET", path, media=True)
        if mime not in {"image/jpeg", "image/png", "image/webp"} or not data:
            raise LibrePhotosError("LibrePhotos returned an unsupported preview.")
        return data, mime
