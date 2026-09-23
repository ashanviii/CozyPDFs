import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cozypdfs.db.models import Book, BookStatus, Job, JobStatus, JobType
from cozypdfs.domain.errors import ConflictError, NotFoundError
from cozypdfs.storage.base import StorageBackend


def create_book(
    db: Session,
    *,
    id: str | None = None,
    owner_id: str,
    title: str | None = None,
    author: str | None = None,
    source_filename: str,
    source_storage_key: str,
    source_hash: str,
    page_count: int | None = None,
    retain_original: bool = True,
) -> Book:
    """Registers a Book row. Upload handling (validation, hashing,
    deduplication, storing the file) lives in domain/uploads.py, which
    calls this once it knows the book is new — this function only owns
    construction of the record itself.

    `id` can be supplied by the caller (uploads.py does this) so the
    storage key can be computed deterministically before the row exists.
    """
    book = Book(
        id=id or str(uuid.uuid4()),
        owner_id=owner_id,
        title=title,
        author=author,
        source_filename=source_filename,
        source_storage_key=source_storage_key,
        source_hash=source_hash,
        page_count=page_count,
        status=BookStatus.PREPARING,
        retain_original=retain_original,
    )
    db.add(book)
    db.flush()
    return book


def list_books_for_owner(db: Session, owner_id: str) -> list[Book]:
    stmt = select(Book).where(Book.owner_id == owner_id).order_by(Book.created_at.desc())
    return list(db.execute(stmt).scalars())


def get_book(db: Session, book_id: str) -> Book | None:
    return db.get(Book, book_id)


def get_owned_book(db: Session, book_id: str, owner_id: str) -> Book:
    """Raises NotFoundError (never a distinct "forbidden") for both a
    missing book and one owned by someone else — ownership isolation means
    not revealing that the book exists at all."""
    book = db.get(Book, book_id)
    if book is None or book.owner_id != owner_id:
        raise NotFoundError(f"book {book_id!r} not found")
    return book


def mark_failed(db: Session, book_id: str, error_message: str) -> None:
    """Called by the worker when a book's conversion job fails permanently.
    Generic on purpose — it doesn't know or care what kind of job failed,
    only that this book's processing did not succeed."""
    book = db.get(Book, book_id)
    if book is None:
        return
    book.status = BookStatus.FAILED
    book.error_message = error_message
    db.flush()


def retry_book(db: Session, book: Book) -> Job:
    if book.status != BookStatus.FAILED:
        raise ConflictError("only a failed book can be retried")

    stmt = (
        select(Job)
        .where(Job.book_id == book.id, Job.job_type == JobType.CONVERT)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    job = db.execute(stmt).scalar_one_or_none()
    if job is None:
        raise ConflictError("no conversion job found for this book")

    job.status = JobStatus.PENDING
    job.attempts = 0
    job.error_message = None
    job.started_at = None
    job.finished_at = None

    book.status = BookStatus.PREPARING
    book.error_message = None

    db.flush()
    return job


def delete_book(db: Session, storage: StorageBackend, book: Book) -> None:
    db.execute(delete(Job).where(Job.book_id == book.id))
    storage.delete_prefix(f"originals/{book.id}")
    storage.delete_prefix(f"books/{book.id}")
    db.delete(book)
    db.flush()
