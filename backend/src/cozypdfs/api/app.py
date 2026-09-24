from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from cozypdfs.api.routes import books, health, me, reader
from cozypdfs.config import get_settings
from cozypdfs.db.session import Database
from cozypdfs.domain import errors
from cozypdfs.domain.uploads import FileTooLargeError
from cozypdfs.storage.local import LocalDiskStorage


def create_app(database: Database | None = None) -> FastAPI:
    """App factory rather than a bare module-level `app` — lets tests inject
    an isolated Database (and, via app.state.settings/storage, isolated
    settings/storage) instead of touching the real ones."""
    settings = get_settings()
    app = FastAPI(title="cozypdfs")

    app.state.settings = settings
    app.state.db = database or Database(settings.database_url)
    app.state.storage = LocalDiskStorage(settings.storage_local_root, settings.storage_local_base_url)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(me.router, prefix="/api")
    app.include_router(books.router, prefix="/api")
    app.include_router(reader.router, prefix="/api")

    # Registered by exact type, most specific first in effect (Starlette
    # walks each exception's MRO and picks the closest match regardless of
    # registration order) — FileTooLargeError gets 413 even though it's
    # also a ValidationError, which everything else maps to 422.
    @app.exception_handler(FileTooLargeError)
    async def _file_too_large_handler(request: Request, exc: FileTooLargeError) -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": str(exc)})

    @app.exception_handler(errors.ValidationError)
    async def _validation_handler(request: Request, exc: errors.ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(errors.ConflictError)
    async def _conflict_handler(request: Request, exc: errors.ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(errors.NotFoundError)
    async def _not_found_handler(request: Request, exc: errors.NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    return app


app = create_app()
