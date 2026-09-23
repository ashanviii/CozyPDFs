"""The worker process. Runs independently of the FastAPI API process (a
separate `python -m cozypdfs.jobs.worker` invocation) so a slow or hung job
can never make the API/reader unresponsive. Talks to the database and to
StorageBackend only — nothing here is specific to what a job actually does,
so real job types (starting with `convert`) plug in via jobs.handlers
without changing this loop.

Every job is bounded by a timeout (`Settings.job_timeout_seconds`), run in
a daemon thread with its own DB session so a hung handler — a pathological
PDF, an infinite loop deep in a C extension — can never block the worker's
main loop. Python has no way to forcibly kill a thread, so a timed-out
handler's thread is abandoned rather than actually stopped; the worker
moves on immediately regardless. See `_run_handler_with_timeout`.
"""

import logging
import threading
import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from cozypdfs.config import get_settings
from cozypdfs.db.models import Job, JobStatus
from cozypdfs.db.session import Database
from cozypdfs.domain import books
from cozypdfs.jobs import queue
from cozypdfs.jobs.handlers import get_handler
from cozypdfs.storage.base import StorageBackend
from cozypdfs.storage.local import LocalDiskStorage

logger = logging.getLogger("cozypdfs.worker")

DEFAULT_JOB_TIMEOUT_SECONDS = 300.0


def run_once(
    session_factory: Callable[[], Session],
    storage: StorageBackend,
    timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS,
) -> bool:
    """Claims and processes a single job, if one is available, bounded by
    `timeout_seconds`. Returns whether a job was processed — used
    directly by tests and by the `--once` CLI mode."""
    session = session_factory()
    try:
        job = queue.claim_next(session)
        if job is None:
            return False
        job_id, job_type = job.id, job.job_type
        session.commit()

        handler = get_handler(job_type)
        if handler is None:
            error: str | None = f"no handler registered for job type {job_type!r}"
        else:
            error = _run_handler_with_timeout(handler, job_id, storage, session_factory, timeout_seconds)

        job = session.get(Job, job_id)
        if error is None:
            queue.complete(session, job)
        else:
            logger.warning("job %s failed: %s", job_id, error)
            queue.fail(session, job, error)
            if job.status == JobStatus.FAILED and job.book_id:
                books.mark_failed(session, job.book_id, error)
        session.commit()
        return True
    finally:
        session.close()


def _run_handler_with_timeout(
    handler: Callable,
    job_id: str,
    storage: StorageBackend,
    session_factory: Callable[[], Session],
    timeout_seconds: float,
) -> str | None:
    """Runs `handler` for `job_id` in a daemon thread with its own,
    independent session (never the caller's — a Session isn't safe to use
    from two threads at once), bounded by `timeout_seconds`.

    Returns None on success, or an error message on failure/timeout. A
    timeout is reported the same way any other handler failure is — fed
    into the caller's existing `queue.fail`/`books.mark_failed` path — so
    retryable vs. permanent, and Book.error_message, all work unchanged.

    If the thread is still alive when this returns, it is abandoned (not
    joined again): there is no way to forcibly cancel a running Python
    thread, so this bounds how long the *worker's main loop* waits, not
    how long the handler itself keeps running. That thread's own session
    is independent, so an eventual late finish or failure there cannot
    corrupt the main loop's bookkeeping — a known, accepted trade-off of
    not introducing separate worker processes/Redis/Celery for this.
    """
    outcome: dict[str, str | None] = {}

    def run() -> None:
        thread_session = session_factory()
        try:
            job = thread_session.get(Job, job_id)
            if job is None:
                raise ValueError(f"job {job_id!r} vanished before its handler ran")
            handler(thread_session, job, storage)
            thread_session.commit()
            outcome["error"] = None
        except Exception as exc:  # noqa: BLE001 - reported to the caller, not re-raised
            thread_session.rollback()
            outcome["error"] = str(exc)
        finally:
            thread_session.close()

    thread = threading.Thread(target=run, name=f"job-{job_id}", daemon=True)
    thread.start()
    thread.join(timeout_seconds)

    if thread.is_alive():
        logger.warning(
            "job %s exceeded %.0fs timeout; abandoning its thread and continuing", job_id, timeout_seconds
        )
        return f"conversion exceeded {timeout_seconds:g}s timeout"

    return outcome.get("error", "handler thread exited without recording a result")


def run_forever(
    database: Database,
    storage: StorageBackend,
    poll_interval: float = 1.0,
    timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS,
) -> None:
    logger.info("worker started, polling every %.1fs, job timeout %.0fs", poll_interval, timeout_seconds)
    while True:
        processed = run_once(database.create_session, storage, timeout_seconds)
        if not processed:
            time.sleep(poll_interval)


def main() -> None:
    import sys

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    database = Database(settings.database_url)
    storage = LocalDiskStorage(settings.storage_local_root, settings.storage_local_base_url)

    if "--once" in sys.argv:
        run_once(database.create_session, storage, settings.job_timeout_seconds)
        return

    run_forever(database, storage, poll_interval=settings.job_poll_interval, timeout_seconds=settings.job_timeout_seconds)


if __name__ == "__main__":
    main()
