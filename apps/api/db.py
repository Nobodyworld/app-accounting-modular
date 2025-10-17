"""Database helpers built on top of SQLModel."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlmodel import SQLModel, Session, create_engine

from .config import settings

__all__ = ["engine", "init_db", "get_session"]

connect_args: dict[str, Any] = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Create all database tables if they do not yet exist."""

    from .models import models  # noqa: F401 - registers SQLModel metadata

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """Provide a SQLModel session suitable for dependency injection."""

    with Session(engine) as session:
        yield session
