"""Reporting endpoints for budgets and forecasts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from ..db import get_session
from ..models.models import Budget
from ..services.budget_service import BudgetReport, BudgetService, CashflowReport
from ..schemas import BudgetReportResponse, CashflowForecastResponse
from ..utils.metadata import (
    merge_forecast_diagnostics,
    prepare_metadata_for_response,
)

router = APIRouter(prefix="/reports", tags=["reports"])


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


def _response_from_budget(report: BudgetReport) -> BudgetReportResponse:
    metadata = _normalised_metadata(report.metadata)

    return BudgetReportResponse(
        lines=[
            {
                "account_id": line.account_id,
                "account_code": line.account_code,
                "account_name": line.account_name,
                "period_start": line.period_start,
                "budget_amount": line.budget_amount,
                "actual_amount": line.actual_amount,
                "variance": line.variance,
                "burn_rate": line.burn_rate,
                "forecast": line.forecast or [],
            }
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
    metadata = _normalised_metadata(report.metadata)
    if report.forecast and report.forecast.diagnostics:
        merge_forecast_diagnostics(metadata, report.forecast.diagnostics)

    return CashflowForecastResponse(
        historical=[{"period": period, "amount": amount} for period, amount in report.historical],
        forecast=report.forecast.points if report.forecast else [],
        model_order=report.forecast.model_order if report.forecast else (0, 0, 0),
        metadata=metadata,
        current_cash=report.current_cash,
        average_monthly_flow=report.average_monthly_flow,
        csv_export=report.csv_export,
    )


def _ensure_budget_scope(
    session: Session, budget_id: int, organization_id: int
) -> None:
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
    session: Session = Depends(get_session),
) -> BudgetReportResponse:
    _ensure_budget_scope(session, budget_id, organization_id)
    service = BudgetService(session)
    effective_horizon = _coerce_optional_int(horizon)
    try:
        report = service.budget_vs_actual(
            budget_id, horizon=effective_horizon, refresh=refresh
        )
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from exc
    return _response_from_budget(report)


@router.get("/cashflow-forecast", response_model=CashflowForecastResponse)
def cashflow_forecast(
    organization_id: int = Query(..., ge=1),
    horizon: int | None = Query(default=None, ge=1),
    refresh: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> CashflowForecastResponse:
    # TODO - Cache refresh results to reduce repeated model runs for identical parameters.
    service = BudgetService(session)
    effective_horizon = _coerce_optional_int(horizon)
    try:
        report = service.cashflow_forecast(
            organization_id, horizon=effective_horizon, refresh=refresh
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND
        if "not found" not in detail.lower():
            status_code = status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return _response_from_cashflow(report)
