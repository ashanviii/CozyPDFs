import time

from cozypdfs.db.models import BookStatus, JobStatus, JobType
from cozypdfs.db.session import Database
from cozypdfs.domain import books
from cozypdfs.jobs import handlers, queue
from cozypdfs.jobs.worker import run_once
from cozypdfs.storage.local import LocalDiskStorage


def test_run_once_processes_a_noop_job_end_to_end(database: Database, storage: LocalDiskStorage):
    session = database.create_session()
    job = queue.enqueue(session, "noop")
    session.commit()
    job_id = job.id
    session.close()

    processed = run_once(database.create_session, storage)

    assert processed is True
    session = database.create_session()
    try:
        finished = session.get(type(job), job_id)
        assert finished.status == JobStatus.READY
    finally:
        session.close()


def test_run_once_returns_false_when_queue_is_empty(database: Database, storage: LocalDiskStorage):
    assert run_once(database.create_session, storage) is False


def test_run_once_marks_unregistered_job_type_as_failed(database: Database, storage: LocalDiskStorage):
    session = database.create_session()
    job = queue.enqueue(session, "totally-unknown-job-type")
    session.commit()
    job_id = job.id
    session.close()

    run_once(database.create_session, storage)

    session = database.create_session()
    try:
        finished = session.get(type(job), job_id)
        assert finished.error_message is not None
        assert finished.status in (JobStatus.PENDING, JobStatus.FAILED)
    finally:
        session.close()


def test_convert_job_for_a_missing_book_fails_cleanly(database: Database, storage: LocalDiskStorage):
    session = database.create_session()
    job = queue.enqueue(session, "convert", book_id="does-not-exist")
    session.commit()
    job_id = job.id
    session.close()

    run_once(database.create_session, storage)

    session = database.create_session()
    try:
        finished = session.get(type(job), job_id)
        assert finished.error_message is not None
        assert "does-not-exist" in finished.error_message
    finally:
        session.close()


# --- timeout behavior --------------------------------------------------


def _register_slow_handler(monkeypatch, sleep_seconds: float, job_type: str = "slow-test-job") -> None:
    def _slow(db, job, storage) -> None:
        time.sleep(sleep_seconds)

    monkeypatch.setitem(handlers._HANDLERS, job_type, _slow)


def test_a_hanging_job_times_out_without_blocking_the_worker(
    database: Database, storage: LocalDiskStorage, monkeypatch
):
    _register_slow_handler(monkeypatch, sleep_seconds=5.0)

    session = database.create_session()
    job = queue.enqueue(session, "slow-test-job")
    session.commit()
    job_id = job.id
    session.close()

    start = time.monotonic()
    processed = run_once(database.create_session, storage, timeout_seconds=0.2)
    elapsed = time.monotonic() - start

    assert processed is True
    assert elapsed < 2.0, "run_once must return promptly once the timeout elapses, not wait for the handler"

    session = database.create_session()
    try:
        finished = session.get(type(job), job_id)
        assert finished.error_message is not None
        assert "timeout" in finished.error_message.lower()
    finally:
        session.close()


def test_a_timed_out_job_is_retryable_like_any_other_failure(
    database: Database, storage: LocalDiskStorage, monkeypatch
):
    _register_slow_handler(monkeypatch, sleep_seconds=5.0)

    session = database.create_session()
    job = queue.enqueue(session, "slow-test-job")
    job.max_attempts = 3
    session.commit()
    job_id = job.id
    session.close()

    run_once(database.create_session, storage, timeout_seconds=0.2)

    session = database.create_session()
    try:
        finished = session.get(type(job), job_id)
        assert finished.status == JobStatus.PENDING  # one attempt left before it's exhausted
        assert finished.attempts == 1
    finally:
        session.close()


def test_repeated_timeouts_eventually_fail_the_job_and_the_book(
    database: Database, storage: LocalDiskStorage, monkeypatch, db_session
):
    _register_slow_handler(monkeypatch, sleep_seconds=5.0, job_type=JobType.CONVERT)

    book = books.create_book(
        db_session,
        owner_id="owner-1",
        source_filename="a.pdf",
        source_storage_key="originals/a/source.pdf",
        source_hash="hash-a",
    )
    job = queue.enqueue(db_session, JobType.CONVERT, book_id=book.id)
    job.max_attempts = 2
    db_session.commit()
    book_id, job_id = book.id, job.id

    run_once(database.create_session, storage, timeout_seconds=0.1)
    run_once(database.create_session, storage, timeout_seconds=0.1)

    session = database.create_session()
    try:
        from cozypdfs.db.models import Book, Job

        finished_job = session.get(Job, job_id)
        assert finished_job.status == JobStatus.FAILED
        assert finished_job.attempts == 2

        finished_book = session.get(Book, book_id)
        assert finished_book.status == BookStatus.FAILED
        assert finished_book.error_message is not None
        assert "timeout" in finished_book.error_message.lower()
    finally:
        session.close()


def test_worker_processes_a_second_job_right_after_a_timeout(
    database: Database, storage: LocalDiskStorage, monkeypatch
):
    """Directly demonstrates the "worker remains alive" requirement: a
    hung job's timeout must not prevent the very next job from being
    claimed and completed normally."""
    _register_slow_handler(monkeypatch, sleep_seconds=5.0)

    session = database.create_session()
    slow_job = queue.enqueue(session, "slow-test-job")
    slow_job.max_attempts = 1  # fails permanently after the first timeout,
    # so the second run_once below claims the next job rather than retrying this one
    fast_job = queue.enqueue(session, "noop")
    session.commit()
    slow_id, fast_id = slow_job.id, fast_job.id
    session.close()

    run_once(database.create_session, storage, timeout_seconds=0.2)
    run_once(database.create_session, storage, timeout_seconds=0.2)

    session = database.create_session()
    try:
        from cozypdfs.db.models import Job

        assert session.get(Job, slow_id).error_message is not None
        assert session.get(Job, fast_id).status == JobStatus.READY
    finally:
        session.close()
