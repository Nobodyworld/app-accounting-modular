"""Regression evidence for resolved post-UX audit findings."""

from __future__ import annotations

import csv
from datetime import date
from io import StringIO
from typing import Any

import pytest
from apps.api.schemas import ForecastRequest, ScenarioBatchRequest, WorkflowIngestRequest
from apps.api.services.budget_service import BudgetService, BudgetVarianceLine
from pydantic import BaseModel


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_budget_csv_neutralizes_formula_prefixes(prefix: str) -> None:
    line = BudgetVarianceLine(
        account_id=1,
        account_code=f"{prefix}AUDIT-CODE",
        account_name=f"{prefix}AUDIT-NAME",
        period_start=date(2026, 1, 1),
        budget_amount=1.0,
        actual_amount=1.0,
        variance=0.0,
        burn_rate=None,
        forecast=None,
    )

    row = next(csv.DictReader(StringIO(BudgetService._render_budget_csv([line]))))

    assert row["account_code"].startswith("'")
    assert row["account_name"].startswith("'")


def _maximum_length(model: type[BaseModel], field_name: str) -> int | None:
    for constraint in model.model_fields[field_name].metadata:
        maximum = getattr(constraint, "max_length", None)
        if isinstance(maximum, int):
            return maximum
    return None


@pytest.mark.parametrize(
    ("model", "field_name"),
    [
        (ForecastRequest, "series"),
        (ScenarioBatchRequest, "scenarios"),
        (WorkflowIngestRequest, "transactions"),
    ],
)
def test_expensive_request_collections_have_maximums(model: type[BaseModel], field_name: str) -> None:
    maximum = _maximum_length(model, field_name)

    assert isinstance(maximum, int)
    assert maximum > 0
    assert maximum <= 10_000


def test_audit_constraint_helper_ignores_unrelated_metadata() -> None:
    class ExampleModel(BaseModel):
        values: list[Any]

    assert _maximum_length(ExampleModel, "values") is None
