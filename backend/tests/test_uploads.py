import hashlib

import pytest
from sqlalchemy import select

from cozypdfs.config import Settings
from cozypdfs.db.models import BookStatus, Job, JobStatus, JobType
from cozypdfs.domain import uploads
from cozypdfs.domain.errors import ValidationError
from tests.factories import make_pdf_bytes


def _settings(**overrides) -> Settings:
    return Settings(cookie_secret="test-secret", **overrides)


def test_valid_upload_creates_book_and_job(db_session, storage):
    data = make_pdf_bytes(pages=2, title="A Book", author="An Author")

    result = uploads.upload_pdf(
        db_session, storage, _settings(), owner_id="owner-1", filename="book.pdf", data=data
    )

    assert result.reused is False
    assert result.book.status == BookStatus.PREPARING
    assert result.book.title == "A Book"
    assert result.book.author == "An Author"
    assert result.book.page_count == 2
    assert result.book.source_filename == "book.pdf"

    job = db_session.execute(select(Job).where(Job.book_id == result.book.id)).scalar_one()
    assert job.job_type == JobType.CONVERT
    assert job.status == JobStatus.PENDING


def test_valid_upload_stores_file_content(db_session, storage):
    data = make_pdf_bytes()

    result = uploads.upload_pdf(
        db_session, storage, _settings(), owner_id="owner-1", filename="book.pdf", data=data
    )

    assert storage.get(result.book.source_storage_key) == data


def test_non_pdf_upload_is_rejected(db_session, storage):
    with pytest.raises(ValidationError):
        uploads.upload_pdf(
            db_session,
            storage,
            _settings(),
            owner_id="owner-1",
            filename="not.pdf",
            data=b"definitely not a pdf",
        )


def test_corrupt_pdf_with_magic_bytes_is_rejected(db_session, storage):
    with pytest.raises(uploads.InvalidPDFError):
        uploads.upload_pdf(
            db_session,
            storage,
            _settings(),
            owner_id="owner-1",
            filename="broken.pdf",
            data=b"%PDF-1.4\ngarbage, not a real pdf body",
        )


def test_oversized_upload_is_rejected(db_session, storage):
    data = make_pdf_bytes()

    with pytest.raises(uploads.FileTooLargeError):
        uploads.upload_pdf(
            db_session,
            storage,
            _settings(max_upload_size_mb=0),
            owner_id="owner-1",
            filename="book.pdf",
            data=data,
        )


def test_too_many_pages_is_rejected(db_session, storage):
    data = make_pdf_bytes(pages=5)

    with pytest.raises(uploads.TooManyPagesError):
        uploads.upload_pdf(
            db_session,
            storage,
            _settings(max_page_count=2),
            owner_id="owner-1",
            filename="book.pdf",
            data=data,
        )


def test_hash_is_deterministic_sha256(db_session, storage):
    data = make_pdf_bytes()

    result = uploads.upload_pdf(
        db_session, storage, _settings(), owner_id="owner-1", filename="book.pdf", data=data
    )

    assert result.book.source_hash == hashlib.sha256(data).hexdigest()


def test_duplicate_upload_by_same_owner_reuses_book(db_session, storage):
    data = make_pdf_bytes()

    first = uploads.upload_pdf(
        db_session, storage, _settings(), owner_id="owner-1", filename="a.pdf", data=data
    )
    second = uploads.upload_pdf(
        db_session, storage, _settings(), owner_id="owner-1", filename="a-again.pdf", data=data
    )

    assert second.reused is True
    assert second.book.id == first.book.id

    jobs = db_session.execute(select(Job).where(Job.book_id == first.book.id)).scalars().all()
    assert len(jobs) == 1


def test_same_content_different_owners_creates_separate_books(db_session, storage):
    data = make_pdf_bytes()

    a = uploads.upload_pdf(
        db_session, storage, _settings(), owner_id="owner-a", filename="book.pdf", data=data
    )
    b = uploads.upload_pdf(
        db_session, storage, _settings(), owner_id="owner-b", filename="book.pdf", data=data
    )

    assert a.book.id != b.book.id
    assert a.reused is False
    assert b.reused is False


def test_upload_recovers_from_a_concurrent_duplicate_insert(monkeypatch, db_session, storage):
    """Simulates the race the unique constraint exists to guard against:
    two uploads of the same file both pass the "does this exist?" check
    before either commits. We can't reliably reproduce that with real
    threads against a single SQLite file in a fast unit test, so instead
    we force the second call's pre-check to miss (as it would mid-race)
    and confirm upload_pdf still recovers via the DB constraint rather
    than creating a duplicate.
    """
    data = make_pdf_bytes()
    first = uploads.upload_pdf(
        db_session, storage, _settings(), owner_id="owner-1", filename="a.pdf", data=data
    )

    real_find = uploads._find_duplicate
    calls = {"n": 0}

    def racy_find(db, owner_id, source_hash):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return real_find(db, owner_id, source_hash)

    monkeypatch.setattr(uploads, "_find_duplicate", racy_find)

    second = uploads.upload_pdf(
        db_session, storage, _settings(), owner_id="owner-1", filename="a-dup.pdf", data=data
    )

    assert second.reused is True
    assert second.book.id == first.book.id

    jobs = db_session.execute(select(Job).where(Job.book_id == first.book.id)).scalars().all()
    assert len(jobs) == 1
