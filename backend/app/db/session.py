"""Database engine and session factory, created lazily on first use.

Importing this module (or anything that imports it transitively — models,
services, tests) never touches settings or opens a connection pool; the
engine binds on the first real database access. That keeps unit tests,
scripts, and tooling free to import application code with no database and
lets tests swap DATABASE_URL before anything connects.

`engine` stays available as a module attribute (PEP 562) for callers and
tests that monkeypatch `session.engine`.
"""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_factory: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
        )
    return _engine


def _get_factory() -> sessionmaker:
    global _factory
    if _factory is None:
        _factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _factory


def SessionLocal() -> Session:  # noqa: N802 — established factory-style name
    """Create a new Session (drop-in for the old sessionmaker instance)."""
    return _get_factory()()


def __getattr__(name: str):
    if name == "engine":
        return get_engine()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    with SessionLocal() as session:
        yield session
