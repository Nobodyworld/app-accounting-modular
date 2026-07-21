"""Focused edge cases for utility-result presentation helpers."""

from __future__ import annotations

from apps.web.utility_results import build_cashflow_result_view, format_number, format_ratio


def test_non_finite_numbers_render_as_unavailable() -> None:
    assert format_number("NaN") == "—"
    assert format_number("Infinity") == "—"
    assert format_ratio("-Infinity") == "—"


def test_zero_cashflow_amounts_are_preserved() -> None:
    view = build_cashflow_result_view(
        {
            "historical": [{"period": "2026-01-01", "amount": 0}],
            "forecast": [["2026-02-01", 0]],
            "metadata": {"reporting_currency": "USD", "forecast_status": "success"},
        }
    )

    assert view.historical_rows == ({"Period": "2026-01-01", "Amount": "USD 0.00"},)
    assert view.forecast_rows == ({"Period": "2026-02-01", "Amount": "USD 0.00"},)
