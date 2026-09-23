from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cozypdfs.db.models import Job, JobStatus


def enqueue(
    db: Session, job_type: str, *, book_id: str | None = None, payload: str | None = None
) -> Job:
    job = Job(job_type=job_type, book_id=book_id, payload=payload, status=JobStatus.PENDING)
    db.add(job)
    db.flush()
    return job


def claim_next(db: Session) -> Job | None:
    """Atomically claims the oldest pending job for this worker.

    Single-writer SQLite makes a plain claim-then-update safe for V1's one
    worker process. Moving to multiple workers on Postgres later means
    swapping this query for `SELECT ... FOR UPDATE SKIP LOCKED` — a
    contained change, since every caller only knows about `claim_next`.
    """
    job = db.execute(
        select(Job).where(Job.status == JobStatus.PENDING).order_by(Job.created_at).limit(1)
    ).scalar_one_or_none()
    if job is None:
        return None

    job.status = JobStatus.PROCESSING
    job.attempts += 1
    job.started_at = datetime.now(UTC)
    db.flush()
    return job


def complete(db: Session, job: Job) -> None:
    job.status = JobStatus.READY
    job.finished_at = datetime.now(UTC)
    db.flush()


def fail(db: Session, job: Job, error: str) -> None:
    job.error_message = error
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(UTC)
    else:
        job.status = JobStatus.PENDING
    db.flush()
