"""Regression coverage for accountant-ready utility result view models."""

from __future__ import annotations

from apps.web.utility_results import (
    build_budget_result_view,
    build_cashflow_result_view,
    build_fx_sync_result_view,
    build_market_sync_result_view,
    format_money,
    format_number,
    format_ratio,
    sanitized_details,
)


def test_decimal_safe_display_formatting() -> None:
    assert format_number("1000.005") == "1,000.01"
    assert format_number(0.1 + 0.2) == "0.30"
    assert format_money("-12.345", " usd ") == "USD -12.35"
    assert format_money(None, "USD") == "USD —"
    assert format_ratio("0.256") == "25.6%"
    assert format_ratio(None) == "—"


def test_sanitized_details_recursively_remove_credentials() -> None:
    access_key = "_".join(("access", "token"))
    session_key = "_".join(("session", "id"))
    payload = {
        "provider": "Example",
        access_key: "remove-me",
        "nested": {
            session_key: "remove-me-too",
            "count": 3,
            "items": [{"password_hint": "remove", "symbol": "AAPL"}],
        },
    }

    assert sanitized_details(payload) == {
        "provider": "Example",
        "nested": {"count": 3, "items": [{"symbol": "AAPL"}]},
    }


def test_budget_result_view_formats_summary_rows_and_csv() -> None:
    payload = {
        "summary": {
            "total_budget": "1000.005",
            "total_actual": "900.1",
            "total_variance": "-99.905",
            "burn_rate": "0.9001",
        },
        "lines": [
            {
                "account_id": 1,
                "account_code": "6100",
                "account_name": "Operations",
                "period_start": "2026-01-01",
                "budget_amount": "1000.005",
                "actual_amount": "900.1",
                "variance": "-99.905",
                "burn_rate": "0.9001",
                "forecast": [["2026-02-01", 950.0]],
            }
        ],
        "metadata": {
            "generated_at": "2026-07-21T00:00:00Z",
            "reporting_currency": "usd",
            "actuals_status": "complete",
        },
        "csv_export": "account,amount\n6100,900.10\n",
    }

    view = build_budget_result_view(payload)

    assert view.state == "success"
    assert view.message == "Budget report is ready for review."
    assert view.currency == "USD"
    assert view.metrics == (
        ("Total budget", "USD 1,000.01"),
        ("Total actual", "USD 900.10"),
        ("Total variance", "USD -99.91"),
        ("Burn rate", "90.0%"),
    )
    assert view.rows == (
        {
            "Account code": "6100",
            "Account": "Operations",
            "Period": "2026-01-01",
            "Budget": "USD 1,000.01",
            "Actual": "USD 900.10",
            "Variance": "USD -99.91",
            "Burn rate": "90.0%",
            "Forecast points": 1,
            "Forecast": [["2026-02-01", 950.0]],
        },
    )
    assert view.warnings == ()
    assert view.csv_export == "account,amount\n6100,900.10\n"


def test_budget_result_view_marks_partial_actuals_and_scrubs_metadata() -> None:
    credential_key = "_".join(("refresh", "token"))
    view = build_budget_result_view(
        {
            "summary": {},
            "lines": [
                {
                    "account_name": "Revenue",
                    "period_start": "2026-01-01",
                    "budget_amount": 0,
                    "actual_amount": 0,
                    "variance": 0,
                    "burn_rate": None,
                }
            ],
            "metadata": {
                "reporting_currency": "EUR",
                "actuals_status": "partial",
                "accounts_without_actuals": [{"account_id": 9}],
                "missing_fx_rates": [{"pair": "USD/EUR"}],
                credential_key: "remove-me",
            },
        }
    )

    assert view.state == "partial"
    assert view.message == "Budget report loaded with review warnings."
    assert view.warnings == (
        "1 account(s) have no actual activity.",
        "1 FX conversion rate(s) were unavailable.",
        "Actuals status: partial.",
    )
    assert credential_key not in view.metadata


def test_budget_result_view_handles_empty_or_malformed_payload() -> None:
    view = build_budget_result_view({"lines": [None, "bad"], "metadata": "bad", "summary": None})

    assert view.state == "empty"
    assert view.rows == ()
    assert view.metrics == (
        ("Total budget", "—"),
        ("Total actual", "—"),
        ("Total variance", "—"),
        ("Burn rate", "—"),
    )
    assert view.csv_export is None


def test_cashflow_result_view_separates_history_forecast_and_diagnostics() -> None:
    secret_key = "_".join(("api", "secret"))
    view = build_cashflow_result_view(
        {
            "historical": [
                {"period": "2026-01-01", "amount": "125.505"},
                {"period": "2026-02-01", "amount": "-25.1"},
            ],
            "forecast": [["2026-03-01", "110.444"]],
            "model_order": [1, 1, 0],
            "current_cash": "100.405",
            "average_monthly_flow": "50.2025",
            "metadata": {
                "reporting_currency": "usd",
                "forecast_status": "success",
                "forecast_diagnostics": {"mae": 1.25, secret_key: "remove-me"},
            },
            "csv_export": "period,amount\n",
        }
    )

    assert view.state == "success"
    assert view.metrics == (
        ("Current cash", "USD 100.41"),
        ("Average monthly flow", "USD 50.20"),
        ("Historical periods", "2"),
        ("Forecast periods", "1"),
    )
    assert view.historical_rows[0] == {"Period": "2026-01-01", "Amount": "USD 125.51"}
    assert view.forecast_rows == ({"Period": "2026-03-01", "Amount": "USD 110.44"},)
    assert view.model_order == "(1, 1, 0)"
    assert view.diagnostics == {"mae": 1.25}
    assert view.csv_export == "period,amount\n"


def test_cashflow_result_view_marks_missing_forecast_as_partial() -> None:
    view = build_cashflow_result_view(
        {
            "historical": [{"period": "2026-01-01", "amount": 10}],
            "forecast": [],
            "metadata": {"forecast_status": "unavailable", "reporting_currency": "USD"},
        }
    )

    assert view.state == "partial"
    assert view.warnings == (
        "Forecast status: unavailable.",
        "Historical activity is available, but no forecast points were returned.",
    )


def test_cashflow_result_view_handles_empty_payload() -> None:
    view = build_cashflow_result_view(None)

    assert view.state == "empty"
    assert view.historical_rows == ()
    assert view.forecast_rows == ()
    assert view.model_order == "Not available"
    assert view.metrics[0] == ("Current cash", "—")


def test_fx_sync_result_views_distinguish_success_and_no_change() -> None:
    success = build_fx_sync_result_view(
        {
            "synced": 4,
            "provider": "European Central Bank",
            "provider_key": "fx:ecb",
            "base": "usd",
            "backfill_days": 2,
        },
        organization_id=7,
    )
    no_change = build_fx_sync_result_view(
        {"synced": 0, "provider": "ECB", "provider_key": "fx:ecb", "base": "EUR"},
        organization_id=9,
    )

    assert success.state == "success"
    assert success.message == "Synchronized 4 FX rate record(s)."
    assert success.subject_value == "USD"
    assert success.effective_range == "Latest plus 2 backfill day(s)"
    assert success.organization_id == 7
    assert no_change.state == "no_change"
    assert no_change.message == "No FX rate changes were persisted."


def test_market_sync_result_views_include_provenance_and_range() -> None:
    view = build_market_sync_result_view(
        {
            "synced": "3",
            "provider": "Yahoo Finance",
            "provider_key": "market:yfinance",
            "symbol": " msft ",
            "start": "2026-01-01",
            "end": "2026-01-31",
        },
        organization_id=12,
    )

    assert view.state == "success"
    assert view.synced_count == 3
    assert view.provider == "Yahoo Finance"
    assert view.provider_key == "market:yfinance"
    assert view.subject_label == "Symbol"
    assert view.subject_value == "MSFT"
    assert view.effective_range == "2026-01-01 through 2026-01-31"
    assert view.organization_id == 12
