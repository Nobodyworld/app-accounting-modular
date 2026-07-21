"""Pure presentation models for protected accounting utility responses.

The Streamlit page should remain responsible for rendering widgets. This module
normalizes API payloads into deterministic, testable view models without
performing accounting calculations or retaining credentials.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

ResultState = Literal["success", "empty", "partial", "no_change"]
_SENSITIVE_KEY_PARTS = ("authorization", "password", "secret", "session", "token")


@dataclass(frozen=True, slots=True)
class BudgetResultView:
    """Accountant-facing budget-vs-actual presentation data."""

    state: ResultState
    message: str
    currency: str | None
    metrics: tuple[tuple[str, str], ...]
    rows: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    metadata: dict[str, Any]
    csv_export: str | None


@dataclass(frozen=True, slots=True)
class CashflowResultView:
    """Accountant-facing cashflow presentation data."""

    state: ResultState
    message: str
    currency: str | None
    metrics: tuple[tuple[str, str], ...]
    historical_rows: tuple[dict[str, str], ...]
    forecast_rows: tuple[dict[str, str], ...]
    model_order: str
    diagnostics: dict[str, Any]
    warnings: tuple[str, ...]
    metadata: dict[str, Any]
    csv_export: str | None


@dataclass(frozen=True, slots=True)
class SyncResultView:
    """Concise provenance and outcome for FX or market synchronization."""

    state: ResultState
    message: str
    synced_count: int
    provider: str | None
    provider_key: str | None
    organization_id: int | None
    subject_label: str
    subject_value: str | None
    effective_range: str | None
    technical_details: dict[str, Any]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return value
    return ()


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return amount if amount.is_finite() else None


def format_number(value: Any, *, places: int = 2) -> str:
    """Format numeric API values without binary floating-point artefacts."""

    amount = _decimal(value)
    if amount is None:
        return "—"
    quantum = Decimal("1").scaleb(-places)
    rounded = amount.quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{rounded:,.{places}f}"


def format_money(value: Any, currency: str | None) -> str:
    """Format a money value with an optional reporting currency."""

    formatted = format_number(value)
    normalized_currency = (currency or "").strip().upper()
    return f"{normalized_currency} {formatted}" if normalized_currency else formatted


def format_ratio(value: Any) -> str:
    """Format a ratio such as burn rate as a percentage."""

    ratio = _decimal(value)
    if ratio is None:
        return "—"
    return f"{(ratio * Decimal('100')).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):,.1f}%"


def sanitized_details(value: Any) -> Any:
    """Recursively remove credential-like fields from technical details."""

    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
                continue
            sanitized[str(key)] = sanitized_details(item)
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [sanitized_details(item) for item in value]
    return value


def build_budget_result_view(payload: Any) -> BudgetResultView:
    """Normalize a budget report response for accountant-facing rendering."""

    root = _mapping(payload)
    metadata = dict(_mapping(root.get("metadata")))
    summary = _mapping(root.get("summary"))
    currency_value = metadata.get("reporting_currency")
    currency = str(currency_value).strip().upper() if currency_value else None
    raw_lines = _sequence(root.get("lines"))

    rows: list[dict[str, Any]] = []
    for item in raw_lines:
        line = _mapping(item)
        if not line:
            continue
        forecast = _sequence(line.get("forecast"))
        rows.append(
            {
                "Account code": line.get("account_code") or "—",
                "Account": line.get("account_name") or "Unnamed account",
                "Period": str(line.get("period_start") or "—"),
                "Budget": format_money(line.get("budget_amount"), currency),
                "Actual": format_money(line.get("actual_amount"), currency),
                "Variance": format_money(line.get("variance"), currency),
                "Burn rate": format_ratio(line.get("burn_rate")),
                "Forecast points": len(forecast),
                "Forecast": list(forecast),
            }
        )

    warnings: list[str] = []
    missing_accounts = _sequence(metadata.get("accounts_without_actuals"))
    missing_fx = _sequence(metadata.get("missing_fx_rates"))
    actuals_status = str(metadata.get("actuals_status") or "").strip().lower()
    if missing_accounts:
        warnings.append(f"{len(missing_accounts)} account(s) have no actual activity.")
    if missing_fx:
        warnings.append(f"{len(missing_fx)} FX conversion rate(s) were unavailable.")
    if actuals_status and actuals_status not in {"complete", "success"}:
        warnings.append(f"Actuals status: {actuals_status}.")

    if not rows:
        state: ResultState = "empty"
        message = "No budget report lines were returned."
    elif warnings:
        state = "partial"
        message = "Budget report loaded with review warnings."
    else:
        state = "success"
        message = "Budget report is ready for review."

    return BudgetResultView(
        state=state,
        message=message,
        currency=currency,
        metrics=(
            ("Total budget", format_money(summary.get("total_budget"), currency)),
            ("Total actual", format_money(summary.get("total_actual"), currency)),
            ("Total variance", format_money(summary.get("total_variance"), currency)),
            ("Burn rate", format_ratio(summary.get("burn_rate"))),
        ),
        rows=tuple(rows),
        warnings=tuple(dict.fromkeys(warnings)),
        metadata=sanitized_details(metadata),
        csv_export=root.get("csv_export")
        if isinstance(root.get("csv_export"), str)
        else None,
    )


def _point_rows(value: Any, *, currency: str | None) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for item in _sequence(value):
        period: Any = None
        amount: Any = None
        if isinstance(item, Mapping):
            period = item.get("period")
            if period is None:
                period = item.get("date")
            if period is None:
                period = item.get("timestamp")
            amount = item.get("amount")
            if amount is None:
                amount = item.get("value")
        elif (
            isinstance(item, Sequence)
            and not isinstance(item, str | bytes | bytearray)
            and len(item) >= 2
        ):
            period, amount = item[0], item[1]
        if period is None:
            continue
        rows.append({"Period": str(period), "Amount": format_money(amount, currency)})
    return tuple(rows)


def build_cashflow_result_view(payload: Any) -> CashflowResultView:
    """Normalize a cashflow forecast response for accountant-facing rendering."""

    root = _mapping(payload)
    metadata = dict(_mapping(root.get("metadata")))
    currency_value = metadata.get("reporting_currency")
    currency = str(currency_value).strip().upper() if currency_value else None
    historical_rows = _point_rows(root.get("historical"), currency=currency)
    forecast_rows = _point_rows(root.get("forecast"), currency=currency)
    diagnostics = dict(_mapping(metadata.get("forecast_diagnostics")))
    forecast_status = str(metadata.get("forecast_status") or "").strip().lower()

    model_order_value = root.get("model_order")
    model_order_parts = _sequence(model_order_value)
    model_order = (
        f"({', '.join(str(part) for part in model_order_parts)})"
        if model_order_parts
        else "Not available"
    )

    warnings: list[str] = []
    if forecast_status and forecast_status not in {"success", "complete"}:
        warnings.append(f"Forecast status: {forecast_status}.")
    if historical_rows and not forecast_rows:
        warnings.append(
            "Historical activity is available, but no forecast points were returned."
        )

    if not historical_rows and not forecast_rows:
        state: ResultState = "empty"
        message = "No historical or forecast cashflow activity was returned."
    elif warnings:
        state = "partial"
        message = "Cashflow report loaded with forecast limitations."
    else:
        state = "success"
        message = "Cashflow report is ready for review."

    return CashflowResultView(
        state=state,
        message=message,
        currency=currency,
        metrics=(
            ("Current cash", format_money(root.get("current_cash"), currency)),
            (
                "Average monthly flow",
                format_money(root.get("average_monthly_flow"), currency),
            ),
            ("Historical periods", str(len(historical_rows))),
            ("Forecast periods", str(len(forecast_rows))),
        ),
        historical_rows=historical_rows,
        forecast_rows=forecast_rows,
        model_order=model_order,
        diagnostics=sanitized_details(diagnostics),
        warnings=tuple(dict.fromkeys(warnings)),
        metadata=sanitized_details(metadata),
        csv_export=root.get("csv_export")
        if isinstance(root.get("csv_export"), str)
        else None,
    )


def _coerce_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced >= 0 else None


def build_fx_sync_result_view(
    payload: Any, *, organization_id: int | None
) -> SyncResultView:
    """Normalize the FX synchronization response."""

    root = _mapping(payload)
    count_value = _coerce_nonnegative_int(root.get("synced"))
    count = count_value or 0
    base = str(root.get("base") or "").strip().upper() or None
    provider = str(root.get("provider") or "").strip() or None
    provider_key = str(root.get("provider_key") or "").strip() or None
    backfill_days = _coerce_nonnegative_int(root.get("backfill_days")) or 0
    if count_value is None:
        state: ResultState = "empty"
        message = "FX synchronization returned no usable result count."
    elif count:
        state = "success"
        message = f"Synchronized {count} FX rate record(s)."
    else:
        state = "no_change"
        message = "No FX rate changes were persisted."
    effective_range = (
        f"Latest plus {backfill_days} backfill day(s)"
        if backfill_days
        else "Latest available rates"
    )
    return SyncResultView(
        state=state,
        message=message,
        synced_count=count,
        provider=provider,
        provider_key=provider_key,
        organization_id=organization_id,
        subject_label="Base currency",
        subject_value=base,
        effective_range=effective_range,
        technical_details=sanitized_details(dict(root)),
    )


def build_market_sync_result_view(
    payload: Any, *, organization_id: int | None
) -> SyncResultView:
    """Normalize the market-price synchronization response."""

    root = _mapping(payload)
    count_value = _coerce_nonnegative_int(root.get("synced"))
    count = count_value or 0
    symbol = str(root.get("symbol") or "").strip().upper() or None
    provider = str(root.get("provider") or "").strip() or None
    provider_key = str(root.get("provider_key") or "").strip() or None
    start = str(root.get("start") or "").strip()
    end = str(root.get("end") or "").strip()
    effective_range = f"{start} through {end}" if start and end else None
    if count_value is None:
        state: ResultState = "empty"
        message = "Market synchronization returned no usable result count."
    elif count:
        state = "success"
        message = f"Synchronized {count} market price record(s)."
    else:
        state = "no_change"
        message = "No market price changes were persisted."
    return SyncResultView(
        state=state,
        message=message,
        synced_count=count,
        provider=provider,
        provider_key=provider_key,
        organization_id=organization_id,
        subject_label="Symbol",
        subject_value=symbol,
        effective_range=effective_range,
        technical_details=sanitized_details(dict(root)),
    )
