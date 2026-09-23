"""The cozypdfs web app: upload a PDF, watch it convert, read it.

A thin HTTP layer over the existing pipeline and library store -- this
file has no reconstruction logic of its own. Routes:

  GET  /                              the single-page app (library + reader)
  POST /api/books                     upload a PDF, starts a background conversion job
  GET  /api/jobs/{job_id}/stream      Server-Sent Events: live conversion progress
  GET  /api/library                   list all books
  GET  /api/library/{id}              one book's metadata
  GET  /api/library/{id}/epub         the generated EPUB (also what the reader fetches)
  GET  /api/library/{id}/cover        cover image, if one was detected
  GET  /api/library/{id}/pdf          the original source PDF ("download the original")
  PATCH /api/library/{id}/progress    persist reading position
  DELETE /api/library/{id}            remove a book
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .jobs import JobManager
from .library import FileSystemLibraryStore, is_valid_book_id

_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200MB -- a generous ceiling for a novel PDF
_PDF_MAGIC = b"%PDF-"

_STATIC_DIR = Path(__file__).parent / "static"
_LIBRARY_ROOT = Path(os.environ.get("COZYPDFS_LIBRARY_DIR", "library_data")).resolve()

library = FileSystemLibraryStore(_LIBRARY_ROOT)
jobs = JobManager(library)

app = FastAPI(title="cozypdfs")


# ---------------------------------------------------------------------------
# Upload + conversion progress
# ---------------------------------------------------------------------------


@app.post("/api/books")
async def upload_book(file: UploadFile = File(...)) -> JSONResponse:
    if file.content_type not in ("application/pdf", "application/octet-stream", None):
        raise HTTPException(400, "That doesn't look like a PDF (unexpected content type).")

    data = await file.read()
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is too large (max {_MAX_UPLOAD_BYTES // (1024*1024)}MB).")
    if not data.startswith(_PDF_MAGIC):
        raise HTTPException(400, "That doesn't look like a valid PDF file.")

    job_id = jobs.start(data, file.filename or "upload.pdf")
    return JSONResponse({"job_id": job_id})


@app.get("/api/jobs/{job_id}/stream")
async def job_stream(job_id: str) -> StreamingResponse:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job.")

    async def event_source():
        while True:
            try:
                event = job.events.get_nowait()
            except queue.Empty:
                if job.done:
                    return
                await asyncio.sleep(0.15)
                continue
            payload = {"stage": event.stage, "message": event.message, "book_id": event.book_id}
            yield f"data: {json.dumps(payload)}\n\n"
            if event.stage in ("added", "error"):
                return

    return StreamingResponse(event_source(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------


@app.get("/api/library")
async def list_library() -> list[dict]:
    return [e.to_dict() for e in library.list()]


@app.get("/api/library/{book_id}")
async def get_book(book_id: str) -> dict:
    entry = _require_entry(book_id)
    return entry.to_dict()


@app.get("/api/library/{book_id}/epub")
async def get_epub(book_id: str) -> FileResponse:
    _require_entry(book_id)
    path = library.epub_path(book_id)
    if path is None:
        raise HTTPException(404, "EPUB not found.")
    return FileResponse(path, media_type="application/epub+zip", filename=f"{book_id}.epub")


@app.get("/api/library/{book_id}/cover")
async def get_cover(book_id: str) -> FileResponse:
    _require_entry(book_id)
    path = library.cover_path(book_id)
    if path is None:
        raise HTTPException(404, "No cover for this book.")
    return FileResponse(path)


@app.get("/api/library/{book_id}/pdf")
async def get_source_pdf(book_id: str) -> FileResponse:
    entry = _require_entry(book_id)
    path = library.source_pdf_path(book_id)
    if path is None:
        raise HTTPException(404, "Original PDF not available.")
    return FileResponse(path, media_type="application/pdf", filename=f"{entry.title}.pdf")


class ProgressUpdate(BaseModel):
    cfi: str | None = None
    percent: float = 0.0


@app.patch("/api/library/{book_id}/progress")
async def update_progress(book_id: str, update: ProgressUpdate) -> dict:
    _require_entry(book_id)
    library.update_progress(book_id, update.cfi, update.percent)
    return {"ok": True}


@app.delete("/api/library/{book_id}")
async def delete_book(book_id: str) -> dict:
    _require_entry(book_id)
    library.delete(book_id)
    return {"ok": True}


def _require_entry(book_id: str):
    if not is_valid_book_id(book_id):
        raise HTTPException(404, "Book not found.")
    entry = library.get(book_id)
    if entry is None:
        raise HTTPException(404, "Book not found.")
    return entry


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")
