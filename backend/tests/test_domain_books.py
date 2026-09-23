import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from cozypdfs.db.models import BookStatus, Job, JobStatus, JobType
from cozypdfs.domain import books
from cozypdfs.domain.errors import ConflictError, NotFoundError
from cozypdfs.domain.identity import IdentityService
from cozypdfs.jobs import queue


def _owner_id(db_session) -> str:
    identity, _ = IdentityService("test-secret").resolve(db_session, None)
    return identity.id


def test_create_book_defaults_to_preparing_status(db_session):
    owner_id = _owner_id(db_session)

    book = books.create_book(
        db_session,
        owner_id=owner_id,
        source_filename="novel.pdf",
        source_storage_key="originals/1/source.pdf",
        source_hash="abc123",
    )

    assert book.status == BookStatus.PREPARING
    assert book.retain_original is True


def test_list_books_for_owner_only_returns_that_owners_books(db_session):
    owner_a = _owner_id(db_session)
    owner_b = _owner_id(db_session)

    books.create_book(
        db_session,
        owner_id=owner_a,
        source_filename="a.pdf",
        source_storage_key="originals/a/source.pdf",
        source_hash="hash-a",
    )
    books.create_book(
        db_session,
        owner_id=owner_b,
        source_filename="b.pdf",
        source_storage_key="originals/b/source.pdf",
        source_hash="hash-b",
    )

    owned_by_a = books.list_books_for_owner(db_session, owner_a)

    assert len(owned_by_a) == 1
    assert owned_by_a[0].source_filename == "a.pdf"


def test_duplicate_owner_and_hash_violates_unique_constraint(db_session):
    books.create_book(
        db_session,
        owner_id="owner-1",
        source_filename="a.pdf",
        source_storage_key="originals/a/source.pdf",
        source_hash="samehash",
    )

    with pytest.raises(IntegrityError):
        books.create_book(
            db_session,
            owner_id="owner-1",
            source_filename="b.pdf",
            source_storage_key="originals/b/source.pdf",
            source_hash="samehash",
        )


def test_get_owned_book_raises_not_found_for_other_owner(db_session):
    book = books.create_book(
        db_session,
        owner_id="owner-1",
        source_filename="a.pdf",
        source_storage_key="originals/a/source.pdf",
        source_hash="hash-a",
    )

    with pytest.raises(NotFoundError):
        books.get_owned_book(db_session, book.id, "owner-2")


def test_get_owned_book_raises_not_found_for_missing_book(db_session):
    with pytest.raises(NotFoundError):
        books.get_owned_book(db_session, "does-not-exist", "owner-1")


def test_mark_failed_sets_book_status_and_error(db_session):
    book = books.create_book(
        db_session,
        owner_id="owner-1",
        source_filename="a.pdf",
        source_storage_key="originals/a/source.pdf",
        source_hash="hash-a",
    )

    books.mark_failed(db_session, book.id, "worker exploded")

    assert book.status == BookStatus.FAILED
    assert book.error_message == "worker exploded"


def test_retry_resets_failed_book_and_job(db_session):
    book = books.create_book(
        db_session,
        owner_id="owner-1",
        source_filename="a.pdf",
        source_storage_key="originals/a/source.pdf",
        source_hash="hash-a",
    )
    job = queue.enqueue(db_session, JobType.CONVERT, book_id=book.id)
    queue.claim_next(db_session)
    job.attempts = job.max_attempts
    queue.fail(db_session, job, "boom")
    books.mark_failed(db_session, book.id, "boom")

    assert book.status == BookStatus.FAILED
    assert job.status == JobStatus.FAILED

    books.retry_book(db_session, book)

    assert book.status == BookStatus.PREPARING
    assert book.error_message is None
    assert job.status == JobStatus.PENDING
    assert job.attempts == 0
    assert job.error_message is None


def test_retry_rejects_a_book_that_is_not_failed(db_session):
    book = books.create_book(
        db_session,
        owner_id="owner-1",
        source_filename="a.pdf",
        source_storage_key="originals/a/source.pdf",
        source_hash="hash-a",
    )

    with pytest.raises(ConflictError):
        books.retry_book(db_session, book)


def test_delete_book_removes_row_jobs_and_storage(db_session, storage):
    book = books.create_book(
        db_session,
        owner_id="owner-1",
        source_filename="a.pdf",
        source_storage_key="placeholder",
        source_hash="hash-a",
    )
    book.source_storage_key = f"originals/{book.id}/source.pdf"
    storage.put(book.source_storage_key, b"pdf bytes")
    queue.enqueue(db_session, JobType.CONVERT, book_id=book.id)

    book_id = book.id
    storage_key = book.source_storage_key

    books.delete_book(db_session, storage, book)

    assert books.get_book(db_session, book_id) is None
    assert not storage.exists(storage_key)
    remaining_jobs = db_session.execute(select(Job).where(Job.book_id == book_id)).scalars().all()
    assert remaining_jobs == []
