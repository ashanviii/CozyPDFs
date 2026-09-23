from cozypdfs.db.models import JobStatus
from cozypdfs.jobs import queue


def test_claim_next_returns_none_when_empty(db_session):
    assert queue.claim_next(db_session) is None


def test_enqueue_then_claim_marks_processing(db_session):
    job = queue.enqueue(db_session, "noop")

    claimed = queue.claim_next(db_session)

    assert claimed.id == job.id
    assert claimed.status == JobStatus.PROCESSING
    assert claimed.attempts == 1
    assert claimed.started_at is not None


def test_claim_next_does_not_return_the_same_job_twice(db_session):
    queue.enqueue(db_session, "noop")

    first = queue.claim_next(db_session)
    second = queue.claim_next(db_session)

    assert first is not None
    assert second is None


def test_complete_marks_job_ready(db_session):
    job = queue.enqueue(db_session, "noop")
    queue.claim_next(db_session)

    queue.complete(db_session, job)

    assert job.status == JobStatus.READY
    assert job.finished_at is not None


def test_fail_retries_until_max_attempts(db_session):
    job = queue.enqueue(db_session, "noop")
    job.max_attempts = 2

    queue.claim_next(db_session)
    queue.fail(db_session, job, "boom")
    assert job.status == JobStatus.PENDING
    assert job.error_message == "boom"

    queue.claim_next(db_session)
    queue.fail(db_session, job, "boom again")
    assert job.status == JobStatus.FAILED
    assert job.finished_at is not None


def test_claim_next_claims_oldest_first(db_session):
    older = queue.enqueue(db_session, "noop")
    queue.enqueue(db_session, "noop")

    claimed = queue.claim_next(db_session)

    assert claimed.id == older.id
