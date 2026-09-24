from collections.abc import Callable

from sqlalchemy.orm import Session

from cozypdfs.conversion.pipeline import reconstruct_pdf
from cozypdfs.db.models import Book, BookStatus, Job, JobType
from cozypdfs.epub.pipeline import build_reader_artifact_and_epub
from cozypdfs.storage.base import StorageBackend

JobHandler = Callable[[Session, Job, StorageBackend], None]

_HANDLERS: dict[str, JobHandler] = {}


def register(job_type: str) -> Callable[[JobHandler], JobHandler]:
    def decorator(fn: JobHandler) -> JobHandler:
        _HANDLERS[job_type] = fn
        return fn

    return decorator


def get_handler(job_type: str) -> JobHandler | None:
    return _HANDLERS.get(job_type)


@register(JobType.NOOP)
def _handle_noop(db: Session, job: Job, storage: StorageBackend) -> None:
    """Exercises the claim -> run -> complete path end-to-end without a
    real pipeline — kept for worker-boundary tests."""
    return


@register(JobType.CONVERT)
def _handle_convert(db: Session, job: Job, storage: StorageBackend) -> None:
    """Runs the PDF reconstruction pipeline for a book and stores the
    resulting DIR. Any failure here (a corrupt page, an assembly bug) just
    raises — the worker's existing generic failure handling (retry, then
    permanent failure + Book.error_message) applies unchanged."""
    if not job.book_id:
        raise ValueError("convert job has no book_id")

    book = db.get(Book, job.book_id)
    if book is None:
        raise ValueError(f"book {job.book_id!r} not found")

    book.status = BookStatus.RECONSTRUCTING
    db.flush()

    pdf_bytes = storage.get(book.source_storage_key)

    document = reconstruct_pdf(
        pdf_bytes,
        storage=storage,
        book_id=book.id,
        title=book.title,
        author=book.author,
    )

    dir_version = (book.dir_version or 0) + 1
    dir_storage_key = f"books/{book.id}/dir/v{dir_version}.json"
    storage.put(
        dir_storage_key, document.model_dump_json().encode("utf-8"), content_type="application/json"
    )

    book.dir_storage_key = dir_storage_key
    book.dir_version = dir_version
    book.status = BookStatus.CREATING_EPUB
    db.flush()

    # Phase 2B: DIR -> reader artifact -> EPUB. Phase 2C's live reader reads
    # the reader artifact directly (see domain/reader.py) — EPUB stays an
    # export-only artifact.
    artifact, epub_bytes = build_reader_artifact_and_epub(document, book_id=book.id, storage=storage)

    epub_version = (book.epub_version or 0) + 1
    reader_artifact_storage_key = f"books/{book.id}/reader_artifact/v{epub_version}.json"
    storage.put(
        reader_artifact_storage_key,
        artifact.model_dump_json().encode("utf-8"),
        content_type="application/json",
    )
    epub_storage_key = f"books/{book.id}/epub/v{epub_version}.epub"
    storage.put(epub_storage_key, epub_bytes, content_type="application/epub+zip")

    book.epub_storage_key = epub_storage_key
    book.epub_version = epub_version
    book.reader_artifact_storage_key = reader_artifact_storage_key
    book.reader_artifact_version = epub_version
    book.status = BookStatus.READY
    book.error_message = None
    db.flush()
