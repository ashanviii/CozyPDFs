from collections.abc import Iterator

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from cozypdfs.config import Settings
from cozypdfs.db.session import Database
from cozypdfs.domain.identity import COOKIE_NAME, IdentityService
from cozypdfs.storage.base import StorageBackend

ONE_YEAR_SECONDS = 60 * 60 * 24 * 365


def get_db(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.db
    session = database.create_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_storage(request: Request) -> StorageBackend:
    return request.app.state.storage


def get_app_settings(request: Request) -> Settings:
    """Reads the settings the app was constructed with (`app.state.settings`)
    rather than the process-wide cached `get_settings()` — this is what lets
    tests override limits per-app-instance instead of fighting the cache."""
    return request.app.state.settings


def get_current_owner_id(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> str:
    service = IdentityService(settings.cookie_secret)
    identity, cookie_value = service.resolve(db, request.cookies.get(COOKIE_NAME))
    response.set_cookie(
        COOKIE_NAME,
        cookie_value,
        httponly=True,
        samesite="lax",
        max_age=ONE_YEAR_SECONDS,
    )
    return identity.id
