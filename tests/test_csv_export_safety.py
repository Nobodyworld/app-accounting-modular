"""Regression coverage for spreadsheet-safe generated CSV exports."""

from __future__ import annotations

import csv
from datetime import date
from io import StringIO

import pytest
from apps.api.services.budget_service import BudgetService, BudgetVarianceLine
from apps.api.utils.csv_safety import safe_csv_text


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_safe_csv_text_neutralizes_formula_prefixes(prefix: str) -> None:
    assert safe_csv_text(f"{prefix}SUM(A1:A2)") == f"'{prefix}SUM(A1:A2)"


def test_safe_csv_text_preserves_normal_text_and_empty_values() -> None:
    assert safe_csv_text("Revenue") == "Revenue"
    assert safe_csv_text(None) == ""


def test_budget_csv_neutralizes_tenant_text_and_preserves_numeric_fields() -> None:
    lines = [
        BudgetVarianceLine(
            account_id=1,
            account_code="=CMD",
            account_name="+Malicious Name",
            period_start=date(2026, 1, 1),
            budget_amount=100.0,
            actual_amount=50.0,
            variance=-50.0,
            burn_rate=0.5,
            forecast=None,
        ),
        BudgetVarianceLine(
            account_id=2,
            account_code="-CODE",
            account_name="@External",
            period_start=date(2026, 2, 1),
            budget_amount=-25.0,
            actual_amount=-10.0,
            variance=15.0,
            burn_rate=None,
            forecast=None,
        ),
    ]

    rows = list(csv.DictReader(StringIO(BudgetService._render_budget_csv(lines))))

    assert rows[0]["account_code"] == "'=CMD"
    assert rows[0]["account_name"] == "'+Malicious Name"
    assert rows[0]["variance"] == "-50.00"
    assert rows[1]["account_code"] == "'-CODE"
    assert rows[1]["account_name"] == "'@External"
    assert rows[1]["budget_amount"] == "-25.00"
    assert rows[1]["actual_amount"] == "-10.00"


def test_cashflow_csv_neutralizes_text_periods_and_preserves_negative_amounts() -> None:
    csv_export = BudgetService._render_cashflow_csv(
        [("=HYPERLINK(\"https://example.invalid\")", -12.5)],
        forecast=None,
    )
    rows = list(csv.reader(StringIO(csv_export)))

    assert rows[1] == ["'=HYPERLINK(\"https://example.invalid\")", "-12.50", "historical"]
