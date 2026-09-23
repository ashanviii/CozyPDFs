import pytest
from fastapi.testclient import TestClient

from cozypdfs.api.app import create_app
from cozypdfs.config import Settings
from cozypdfs.db.base import Base
from cozypdfs.db.session import Database
from cozypdfs.storage.local import LocalDiskStorage


@pytest.fixture
def database(tmp_path) -> Database:
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(db.engine)
    return db


@pytest.fixture
def db_session(database: Database):
    session = database.create_session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def storage(tmp_path) -> LocalDiskStorage:
    return LocalDiskStorage(tmp_path / "storage")


@pytest.fixture
def settings() -> Settings:
    return Settings(cookie_secret="test-secret")


@pytest.fixture
def app(database: Database, storage: LocalDiskStorage, settings: Settings):
    app = create_app(database=database)
    app.state.storage = storage
    app.state.settings = settings
    return app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)
