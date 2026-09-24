from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cozypdfs.db.models import Book, ReadingProgress


class BookOut(BaseModel):
    """The book shape exposed to the frontend. Deliberately excludes
    `source_storage_key`/`dir_storage_key` — raw storage locations never
    leave the backend."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    author: str | None
    source_filename: str
    status: str
    page_count: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, book: Book) -> "BookOut":
        return cls.model_validate(book)


class UploadResponse(BaseModel):
    book: BookOut
    reused: bool


ReaderMode = Literal["scroll", "paginated"]


class ProgressIn(BaseModel):
    chapter_id: str
    block_id: str
    character_offset: int = Field(ge=0)
    mode: ReaderMode


class ProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chapter_id: str
    block_id: str
    character_offset: int
    mode: str
    updated_at: datetime

    @classmethod
    def from_model(cls, progress: ReadingProgress) -> "ProgressOut":
        return cls.model_validate(progress)
