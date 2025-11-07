"""Database helpers built on top of SQLModel."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

__all__ = ["engine", "init_db", "get_session"]

database_url = settings.database_url
url = make_url(database_url)

connect_args: dict[str, Any] = {}
engine_kwargs: dict[str, Any] = {"echo": False}

# Track engines that have already had metadata created so repeated dependency
# injections in tests do not try to re-run expensive schema creation.
_initialised_engines: set[int] = set()

if url.get_backend_name() == "sqlite":
    connect_args = {"check_same_thread": False}
    engine_kwargs["connect_args"] = connect_args

    if url.database in (None, "", ":memory:"):
        # Ensure in-memory SQLite databases are shared across connections. This is
        # essential for FastAPI tests that spin up multiple sessions against the
        # same engine instance.
        engine_kwargs["poolclass"] = StaticPool

engine = create_engine(database_url, **engine_kwargs)


def init_db() -> None:
    """Create all database tables if they do not yet exist."""

    from .models import models  # noqa: F401 - registers SQLModel metadata

    # TODO - Migrate towards Alembic-managed schema evolutions instead of create_all.
    SQLModel.metadata.create_all(engine)
    _initialised_engines.add(id(engine))


def get_session() -> Generator[Session, None, None]:
    """Provide a SQLModel session suitable for dependency injection."""

    with Session(engine, expire_on_commit=False) as session:
        bind = session.get_bind()
        if bind is not None:
            bind_identifier = id(bind)
            if bind_identifier not in _initialised_engines:
                SQLModel.metadata.create_all(bind)
                _initialised_engines.add(bind_identifier)
                # TODO - Replace eager create_all with idempotent migration bootstrapping.
        yield session
