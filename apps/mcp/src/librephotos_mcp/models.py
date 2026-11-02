"""Bounded tool schemas. Unknown upstream fields never reach MCP clients."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

Limit = Annotated[int, Field(ge=1, le=100)]
PageNumber = Annotated[int, Field(ge=1, le=100000)]
ShortText = Annotated[str, Field(max_length=16384)]


class PhotoSummary(BaseModel):
    id: UUID
    image_hash: str = Field(pattern=r"^[a-f0-9]{32,64}$")
    date: ShortText = ""
    location: ShortText | None = None
    type: Annotated[str, Field(pattern=r"^(image|video|motion_photo)$")] = "image"


class Album(BaseModel):
    id: int
    title: str = Field(max_length=512)


class Person(BaseModel):
    id: int
    name: str = Field(max_length=512)


class PhotoPerson(BaseModel):
    name: str = Field(max_length=512)
    face_id: int | None = None


class PhotoDetail(BaseModel):
    id: UUID
    image_hash: str = Field(pattern=r"^[a-f0-9]{32,64}$")
    exif_timestamp: ShortText | None = None
    caption: ShortText | None = None
    people: Annotated[list[PhotoPerson], Field(max_length=100)] | None = None
    album_refs: Annotated[list[Album], Field(max_length=100)] | None = None
    width: int | None = None
    height: int | None = None
    rating: int | None = None
    video: bool = False
    square_thumbnail_url: str = Field(default="", max_length=2048, exclude=True)


class Page[T: BaseModel](BaseModel):
    count: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    num_pages: int = Field(ge=1)
    results: Annotated[list[T], Field(max_length=100)]


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    taken_after: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    taken_before: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    person: Annotated[list[Annotated[int, Field(ge=1)]], Field(max_length=20)] | None = None
    album_id: int | None = Field(default=None, ge=1)
    camera: str | None = Field(default=None, min_length=1, max_length=100)
    rating_min: int | None = Field(default=None, ge=1, le=5)
    file_type: str | None = Field(default=None, pattern=r"^(image|raw|video)$")


class JobStatus(BaseModel):
    job_id: UUID
    finished: bool
    failed: bool
    cancelled: bool
    progress_current: int
    progress_target: int
    progress_step: ShortText | None = None
    started_at: ShortText | None = None
    finished_at: ShortText | None = None
    errors: Annotated[list[str], Field(max_length=100)] = Field(default_factory=list)
    error_count: int = Field(default=0, ge=0)


class JobStarted(BaseModel):
    job_id: UUID


class FileExists(BaseModel):
    exists: bool
    photo_id: UUID | None = None


class OperationResult(BaseModel):
    success: bool = True


class AlbumPhotos(Page[PhotoSummary]):
    album: Album


class UpstreamJob(JobStatus):
    result: JsonValue = None
