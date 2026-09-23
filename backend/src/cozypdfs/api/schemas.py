from datetime import datetime

from pydantic import BaseModel, ConfigDict

from cozypdfs.db.models import Book


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
