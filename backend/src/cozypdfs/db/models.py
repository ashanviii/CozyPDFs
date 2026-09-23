import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from cozypdfs.db.base import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Identity(Base):
    """An anonymous, server-side owner of a library. The browser only ever
    holds a signed pointer to this row (see domain/identity.py) — all real
    state lives here, not in localStorage. `claimed_by_user_id` is unused
    until real accounts exist; claiming later means setting this field, not
    migrating owner_id across every table.
    """

    __tablename__ = "identities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    claimed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class BookStatus(StrEnum):
    UPLOADING = "uploading"  # reserved for a future chunked/resumable upload; not set today
    PREPARING = "preparing"
    RECONSTRUCTING = "reconstructing"
    CREATING_EPUB = "creating_epub"
    READY = "ready"
    FAILED = "failed"


class Book(Base):
    """A book owned by an Identity. `dir_storage_key`/`dir_version` point at
    the canonical Document Intermediate Representation artifact in storage —
    the DIR itself is not normalized into rows here (see cozypdfs.dir).

    The (owner_id, source_hash) unique constraint is what makes duplicate
    upload detection race-safe: two concurrent uploads of the same file by
    the same owner can both pass an in-memory "does this exist?" check
    before either commits, but only one INSERT can win here.
    """

    __tablename__ = "books"
    __table_args__ = (
        UniqueConstraint("owner_id", "source_hash", name="uq_books_owner_source_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("identities.id"), nullable=False, index=True
    )

    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    author: Mapped[str | None] = mapped_column(String(512), nullable=True)

    source_filename: Mapped[str] = mapped_column(String(512))
    source_storage_key: Mapped[str] = mapped_column(String(512))
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retain_original: Mapped[bool] = mapped_column(Boolean, default=True)

    status: Mapped[str] = mapped_column(String(32), default=BookStatus.PREPARING)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    dir_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dir_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class JobType(StrEnum):
    CONVERT = "convert"  # registered by the conversion pipeline in a later phase
    NOOP = "noop"  # exercises the worker boundary without a real pipeline


class Job(Base):
    """A unit of async work claimed by the worker process. `book_id` is
    nullable so infrastructure-only jobs (like `noop`) don't need a book.
    """

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    book_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("books.id"), nullable=True, index=True
    )
    job_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.PENDING, index=True)

    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
