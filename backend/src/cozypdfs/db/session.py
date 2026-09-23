from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class Database:
    """Wraps an engine + session factory for one database URL.

    Instantiated once per process (API app, worker, or a test fixture) rather
    than relying on a hidden global, so tests can point it at an isolated
    database without monkeypatching module state.
    """

    def __init__(self, database_url: str):
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_session(self) -> Session:
        return self.session_factory()
