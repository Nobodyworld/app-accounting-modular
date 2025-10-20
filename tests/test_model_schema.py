from sqlalchemy import inspect
from sqlmodel import SQLModel, create_engine

from apps.api.models import models  # noqa: F401 - ensure metadata registration


def _create_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_price_unique_constraint() -> None:
    engine = _create_engine()
    try:
        inspector = inspect(engine)
        uniques = inspector.get_unique_constraints("price")
        assert any(
            set(constraint["column_names"]) == {"instrument_id", "date", "provider"}
            for constraint in uniques
        )
    finally:
        engine.dispose()


def test_rate_composite_index() -> None:
    engine = _create_engine()
    try:
        inspector = inspect(engine)
        indexes = inspector.get_indexes("rate")
        assert any(
            index["name"] == "ix_rate_base_quote_date_provider"
            and index["column_names"] == ["base", "quote", "date", "provider"]
            for index in indexes
        )
    finally:
        engine.dispose()
