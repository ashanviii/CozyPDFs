# cozypdfs

A web-based ebook reader: upload a PDF, it's reconstructed into a clean,
reflowable reading experience — no manual conversion, no PDF-page-viewer UX.

## Status

**Phase 1 — PDF upload → Library.** Users can upload a PDF, it's validated
(magic bytes + PyMuPDF), deduplicated per owner, stored, and appears in a
real Library UI showing its processing state. **PDF → EPUB conversion is
still not implemented** — no handler is registered for the `convert` job
type yet, so uploaded books stay in `preparing` until Phase 2. Don't run
the worker continuously against a real deployment yet: since `convert`
jobs currently have no handler, the worker will exhaust their retries and
mark them `failed` with a "no handler registered" error. Running the
worker is only useful today for exercising the job-queue machinery itself
(see `tests/test_worker.py`).

The reader itself, folders, bookmarks, search, TTS, and ambient audio are
still not implemented. See the architecture discussion in-repo history for
the full design (DIR as canonical model, anonymous server-side identity,
`StorageBackend` abstraction, preservation-first conversion strategy).

## Layout

```
backend/    FastAPI API + conversion worker (Python, uv)
frontend/   React + Vite reader/library UI
```

## Backend

```bash
cd backend
uv sync
cp .env.example .env      # adjust as needed
uv run alembic upgrade head
uv run uvicorn cozypdfs.api.app:app --reload --port 8000
```

Run the worker (separate process, polls the job queue):

```bash
uv run python -m cozypdfs.jobs.worker
```

Run tests:

```bash
uv run pytest
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Dev server proxies `/api` and `/storage` to `http://localhost:8000`.
