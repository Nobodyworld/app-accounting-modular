"""Schema metadata tests ensuring constraints and indexes exist as expected."""

from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

from apps.api.models import models  # noqa: F401 - ensure metadata registration


def _create_engine():
    """Initialise an in-memory engine and create all SQLModel tables."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_price_unique_constraint() -> None:
    """Ensure daily prices cannot be duplicated for provider/instrument pairs."""
    engine = _create_engine()
    try:
        inspector = inspect(engine)
        uniques = inspector.get_unique_constraints("price")
        assert any(set(constraint["column_names"]) == {"instrument_id", "date", "provider"} for constraint in uniques)
    finally:
        engine.dispose()


def test_rate_composite_index() -> None:
    """Validate the FX rate composite index is created with correct ordering."""
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


# TODO - (models) Extend constraint checks to workflow and audit tables.
