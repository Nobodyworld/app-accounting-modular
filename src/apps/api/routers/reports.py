"""Reporting endpoints for budgets and forecasts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session

from ..db import get_session
from ..models.models import Budget
from ..schemas import (
    BudgetReportLineSchema,
    BudgetReportResponse,
    CashflowForecastResponse,
    ReportMetadata,
)
from ..services.budget_service import BudgetReport, BudgetService, CashflowReport
from ..utils.metadata import (
    merge_forecast_diagnostics,
    prepare_metadata_for_response,
)

router = APIRouter(prefix="/reports", tags=["reports"])
_cashflow_cache: dict[tuple[int, int | None], tuple[CashflowReport, float]] = {}
_CACHE_TTL_SECONDS = 300


def _normalised_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    return prepare_metadata_for_response(metadata)


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced


def _coerce_positive_int(value: Any, *, default: int, minimum: int = 0, maximum: int | None = None) -> int:
    """Return a coerced integer within the provided bounds."""

    try:
        coerced = int(value)
    except (TypeError, ValueError):
        coerced = default
    if coerced < minimum:
        coerced = minimum
    if maximum is not None and coerced > maximum:
        coerced = maximum
    return coerced


def _response_from_budget(report: BudgetReport) -> BudgetReportResponse:
    metadata = ReportMetadata.model_validate(_normalised_metadata(report.metadata))

    return BudgetReportResponse(
        lines=[
            BudgetReportLineSchema(
                account_id=line.account_id,
                account_code=line.account_code,
                account_name=line.account_name,
                period_start=line.period_start,
                budget_amount=line.budget_amount,
                actual_amount=line.actual_amount,
                variance=line.variance,
                burn_rate=line.burn_rate,
                forecast=line.forecast or [],
            )
            for line in report.lines
        ],
        summary={
            "total_budget": report.total_budget,
            "total_actual": report.total_actual,
            "total_variance": report.total_variance,
            "burn_rate": report.burn_rate,
        },
        metadata=metadata,
        csv_export=report.csv_export,
    )


def _response_from_cashflow(report: CashflowReport) -> CashflowForecastResponse:
    metadata_dict = _normalised_metadata(report.metadata)
    if report.forecast and report.forecast.diagnostics:
        merge_forecast_diagnostics(metadata_dict, report.forecast.diagnostics)
    metadata = ReportMetadata.model_validate(metadata_dict)

    return CashflowForecastResponse(
        historical=[{"period": period, "amount": amount} for period, amount in report.historical],
        forecast=report.forecast.points if report.forecast else [],
        model_order=report.forecast.model_order if report.forecast else (0, 0, 0),
        metadata=metadata,
        current_cash=report.current_cash,
        average_monthly_flow=report.average_monthly_flow,
        csv_export=report.csv_export,
    )


def _ensure_budget_scope(session: Session, budget_id: int, organization_id: int) -> None:
    budget = session.get(Budget, budget_id)
    if budget is None or budget.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found for organisation",
        )


@router.get("/budget-vs-actual", response_model=BudgetReportResponse)
def budget_vs_actual(
    budget_id: int = Query(..., ge=1),
    organization_id: int = Query(..., ge=1),
    horizon: int | None = Query(default=None, ge=1),
    refresh: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> BudgetReportResponse:
    """Return a budget variance view, optionally forcing a recalculation."""

    _ensure_budget_scope(session, budget_id, organization_id)
    service = BudgetService(session)
    effective_horizon = _coerce_optional_int(horizon)
    try:
        report = service.budget_vs_actual(budget_id, horizon=effective_horizon, refresh=refresh)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from exc
    total_lines = len(report.lines)
    safe_limit = _coerce_positive_int(limit, default=500, minimum=1, maximum=5000)
    safe_offset = _coerce_positive_int(offset, default=0, minimum=0)
    paged_report = BudgetReport(
        lines=report.lines[safe_offset : safe_offset + safe_limit],
        total_budget=report.total_budget,
        total_actual=report.total_actual,
        total_variance=report.total_variance,
        burn_rate=report.burn_rate,
        metadata={
            **report.metadata,
            "total_lines": total_lines,
            "limit": safe_limit,
            "offset": safe_offset,
        },
        csv_export=report.csv_export,
    )
    return _response_from_budget(paged_report)


@router.get("/cashflow-forecast", response_model=CashflowForecastResponse)
def cashflow_forecast(
    organization_id: int,
    horizon: int | None = None,
    refresh: bool = False,
    stream_csv: bool = False,
    session: Session = Depends(get_session),
) -> CashflowForecastResponse | Response:
    """Return a rolling cashflow forecast for an organisation."""

    stream_csv = bool(stream_csv)
    if stream_csv:
        refresh = True
    effective_horizon = _coerce_optional_int(horizon)
    key = (organization_id, effective_horizon)
    now = datetime.now().timestamp()
    if not refresh:
        cached = _cashflow_cache.get(key)
        if cached and (now - cached[1]) < _CACHE_TTL_SECONDS:
            return _response_from_cashflow(cached[0])
    service = BudgetService(session)
    try:
        report = service.cashflow_forecast(organization_id, horizon=effective_horizon, refresh=refresh)
        _cashflow_cache[key] = (report, now)
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND
        if "not found" not in detail.lower():
            status_code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc

    if stream_csv:
        if not report.csv_export:
            raise HTTPException(status_code=400, detail="CSV export unavailable for this report")
        return Response(content=report.csv_export, media_type="text/csv")

    return _response_from_cashflow(report)
