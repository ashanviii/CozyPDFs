"""Upload orchestration: validates a PDF, deduplicates it against the
owner's existing library, stores it, and registers a conversion job.
"""

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cozypdfs.config import Settings
from cozypdfs.db.models import Book, JobType
from cozypdfs.domain import books, pdf_validation
from cozypdfs.domain.errors import ValidationError
from cozypdfs.jobs import queue
from cozypdfs.storage.base import StorageBackend

InvalidPDFError = pdf_validation.InvalidPDFError


class FileTooLargeError(ValidationError):
    pass


class TooManyPagesError(ValidationError):
    pass


@dataclass
class UploadResult:
    book: Book
    reused: bool


def _source_storage_key(book_id: str) -> str:
    return f"originals/{book_id}/source.pdf"


def _hash_content(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _find_duplicate(db: Session, owner_id: str, source_hash: str) -> Book | None:
    stmt = select(Book).where(Book.owner_id == owner_id, Book.source_hash == source_hash)
    return db.execute(stmt).scalar_one_or_none()


def upload_pdf(
    db: Session,
    storage: StorageBackend,
    settings: Settings,
    *,
    owner_id: str,
    filename: str,
    data: bytes,
) -> UploadResult:
    """Validates, deduplicates, stores, and registers an uploaded PDF.

    Duplicate detection is scoped to (owner_id, source_hash) and is race-safe:
    the fast-path check below is an optimization (skips storage/PDF-parsing
    work for the common case), but the actual guarantee comes from the
    `uq_books_owner_source_hash` unique constraint on Book — if two uploads
    of the same file race past the fast-path check together, only one INSERT
    wins and the loser transparently reuses the winner's book instead of
    erroring.

    Scoping the key to owner_id (rather than source_hash alone) keeps this
    compatible with a future *global* conversion cache: that would key on
    source_hash across all owners and let the (not yet built) convert job
    handler populate Book.dir_storage_key from a shared artifact instead of
    re-running the pipeline — a change contained entirely to that handler,
    not to this upload flow or the ownership model.
    """
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise FileTooLargeError(f"file exceeds {settings.max_upload_size_mb}MB limit")

    if not pdf_validation.has_pdf_magic_bytes(data):
        raise pdf_validation.InvalidPDFError("file does not look like a PDF")

    source_hash = _hash_content(data)

    existing = _find_duplicate(db, owner_id, source_hash)
    if existing is not None:
        return UploadResult(book=existing, reused=True)

    info = pdf_validation.extract_pdf_info(data)
    if info.page_count > settings.max_page_count:
        raise TooManyPagesError(
            f"PDF has {info.page_count} pages, exceeding the {settings.max_page_count} page limit"
        )

    book_id = str(uuid.uuid4())
    storage_key = _source_storage_key(book_id)

    savepoint = db.begin_nested()
    try:
        book = books.create_book(
            db,
            id=book_id,
            owner_id=owner_id,
            title=info.title,
            author=info.author,
            source_filename=filename,
            source_storage_key=storage_key,
            source_hash=source_hash,
            page_count=info.page_count,
            retain_original=settings.retain_original_pdfs,
        )
        savepoint.commit()
    except IntegrityError:
        savepoint.rollback()
        existing = _find_duplicate(db, owner_id, source_hash)
        if existing is not None:
            return UploadResult(book=existing, reused=True)
        raise

    storage.put(storage_key, data, content_type="application/pdf")
    queue.enqueue(db, JobType.CONVERT, book_id=book.id)

    return UploadResult(book=book, reused=False)
