"""End-to-end integration: upload a real PDF through the same domain
function the API uses, let the real worker claim and run the real
`convert` job handler, and confirm the book ends up `ready` with a valid,
storage-backed DIR *and* EPUB — the full Phase 2A + Phase 2B pipeline
running through the actual async job system, not just called directly."""

from pathlib import Path

from cozypdfs.config import Settings
from cozypdfs.db.models import BookStatus, JobStatus
from cozypdfs.db.session import Database
from cozypdfs.dir.schema import DIRDocument
from cozypdfs.domain import uploads
from cozypdfs.epub.validation import validate as validate_epub
from cozypdfs.jobs.worker import run_once
from cozypdfs.storage.local import LocalDiskStorage

GOLDEN_PDF = Path(__file__).parent / "golden_pdfs" / "single_column_prose.pdf"


def _settings() -> Settings:
    return Settings(cookie_secret="test-secret")


def test_upload_then_worker_run_produces_a_ready_book_with_a_valid_dir(
    database: Database, storage: LocalDiskStorage, db_session
):
    data = GOLDEN_PDF.read_bytes()
    result = uploads.upload_pdf(
        db_session, storage, _settings(), owner_id="owner-1", filename="book.pdf", data=data
    )
    db_session.commit()
    book_id = result.book.id

    processed = run_once(database.create_session, storage)
    assert processed is True

    session = database.create_session()
    try:
        from cozypdfs.db.models import Book, Job

        book = session.get(Book, book_id)
        assert book.status == BookStatus.READY
        assert book.error_message is None
        assert book.dir_storage_key is not None
        assert book.dir_version == 1
        assert book.epub_storage_key is not None
        assert book.epub_version == 1

        job = session.query(Job).filter(Job.book_id == book_id).one()
        assert job.status == JobStatus.READY
    finally:
        session.close()

    dir_bytes = storage.get(book.dir_storage_key)
    document = DIRDocument.model_validate_json(dir_bytes)
    assert document.chapters
    assert any("bright cold day" in block.content for chapter in document.chapters for block in chapter.blocks)

    epub_bytes = storage.get(book.epub_storage_key)
    assert validate_epub(epub_bytes) == []


def test_retry_after_a_transient_failure_reruns_the_pipeline(
    database: Database, storage: LocalDiskStorage, db_session, monkeypatch
):
    data = GOLDEN_PDF.read_bytes()
    result = uploads.upload_pdf(
        db_session, storage, _settings(), owner_id="owner-1", filename="book.pdf", data=data
    )
    db_session.commit()
    book_id = result.book.id

    # Force the first attempt to fail, independent of the real pipeline.
    import cozypdfs.jobs.handlers as handlers_module

    original = handlers_module.reconstruct_pdf
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated transient failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(handlers_module, "reconstruct_pdf", flaky)

    first = run_once(database.create_session, storage)
    assert first is True

    session = database.create_session()
    try:
        from cozypdfs.db.models import Book

        book = session.get(Book, book_id)
        # The failed attempt's handler runs in its own session (needed for
        # the timeout mechanism) and rolls back on failure, so a
        # not-yet-exhausted retry leaves the book exactly where it was
        # before that attempt — not stuck showing a stale "reconstructing"
        # for a change that was never actually committed.
        assert book.status == BookStatus.PREPARING
    finally:
        session.close()

    second = run_once(database.create_session, storage)
    assert second is True

    session = database.create_session()
    try:
        from cozypdfs.db.models import Book

        book = session.get(Book, book_id)
        assert book.status == BookStatus.READY
    finally:
        session.close()
