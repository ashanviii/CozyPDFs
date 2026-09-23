"""Background conversion jobs with live progress.

The upload flow must feel polished -- "Analyzing your book... Reconstructing
chapters... Building your EPUB..." -- rather than a blank spinner, and it
must not block the HTTP request for however long conversion takes. Each
upload starts a background thread running `ConversionPipeline.convert`
with an `on_progress` callback that pushes events onto a queue; the SSE
route in `app.py` drains that queue to the browser as it happens.
"""

from __future__ import annotations

import queue
import re
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..exceptions import CozyPdfsError
from ..pipeline import ConversionPipeline
from .library import FileSystemLibraryStore

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9 ._-]")


@dataclass(slots=True)
class JobEvent:
    stage: str
    message: str
    book_id: str | None = None


class ConversionJob:
    def __init__(self, job_id: str):
        self.id = job_id
        self.events: "queue.Queue[JobEvent]" = queue.Queue()
        self.done = False
        self.error: str | None = None
        self.book_id: str | None = None


class JobManager:
    def __init__(self, library: FileSystemLibraryStore, pipeline: ConversionPipeline | None = None):
        self.library = library
        self.pipeline = pipeline or ConversionPipeline()
        self._jobs: dict[str, ConversionJob] = {}
        self._lock = threading.Lock()

    def start(self, pdf_bytes: bytes, original_filename: str) -> str:
        job_id = uuid.uuid4().hex
        job = ConversionJob(job_id)
        with self._lock:
            self._jobs[job_id] = job
        thread = threading.Thread(
            target=self._run, args=(job, pdf_bytes, original_filename), daemon=True
        )
        thread.start()
        return job_id

    def get(self, job_id: str) -> ConversionJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run(self, job: ConversionJob, pdf_bytes: bytes, original_filename: str) -> None:
        try:
            job.events.put(JobEvent(stage="uploading", message="Uploading..."))
            with tempfile.TemporaryDirectory(prefix="cozypdfs_upload_") as tmp:
                tmp_dir = Path(tmp)
                pdf_path = tmp_dir / _safe_filename(original_filename)
                pdf_path.write_bytes(pdf_bytes)
                epub_path = tmp_dir / "book.epub"

                def on_progress(stage: str, message: str) -> None:
                    job.events.put(JobEvent(stage=stage, message=message))

                result = self.pipeline.convert(pdf_path, epub_path, on_progress=on_progress)
                book_id = self.library.add(result.book, result.epub_path, pdf_path)
                job.book_id = book_id
                job.events.put(
                    JobEvent(stage="added", message="Added to your library.", book_id=book_id)
                )
        except CozyPdfsError as exc:
            job.error = str(exc)
            job.events.put(JobEvent(stage="error", message=str(exc)))
        except Exception as exc:  # never let an unexpected failure hang the UI
            job.error = f"Something went wrong during conversion: {exc}"
            job.events.put(JobEvent(stage="error", message=job.error))
        finally:
            job.done = True


def _safe_filename(name: str) -> str:
    """Strip any path components and unsafe characters from a client-supplied
    filename before it ever touches the filesystem."""
    base = Path(name).name
    base = _SAFE_NAME_RE.sub("_", base) or "upload"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base
