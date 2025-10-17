"""Database helpers built on top of SQLModel."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from .config import settings

__all__ = ["engine", "init_db", "get_session"]

database_url = settings.database_url
url = make_url(database_url)

connect_args: dict[str, Any] = {}
engine_kwargs: dict[str, Any] = {"echo": False}

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

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """Provide a SQLModel session suitable for dependency injection."""

    with Session(engine) as session:
        bind = session.get_bind()
        if bind is not None and not getattr(bind, "_ma_tables_initialized", False):
            SQLModel.metadata.create_all(bind)
            setattr(bind, "_ma_tables_initialized", True)
        yield session
