"""Reporting endpoints for budgets and forecasts."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from ..db import get_session
from ..services.budget_service import BudgetReport, BudgetService, CashflowReport
from ..schemas import BudgetReportResponse, CashflowForecastResponse

router = APIRouter(prefix="/reports", tags=["reports"])


def _response_from_budget(report: BudgetReport) -> BudgetReportResponse:
    metadata = report.metadata.copy()
    # TODO - Normalize metadata keys/values to ensure downstream clients see consistent casing.
    generated_at = metadata.get("generated_at")
    if isinstance(generated_at, str):
        metadata["generated_at"] = datetime.fromisoformat(generated_at)

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
    metadata = report.metadata.copy()
    # TODO - Attach model diagnostics to metadata for observability of forecast quality.
    generated_at = metadata.get("generated_at")
    if isinstance(generated_at, str):
        metadata["generated_at"] = datetime.fromisoformat(generated_at)

    return CashflowForecastResponse(
        historical=[{"period": period, "amount": amount} for period, amount in report.historical],
        forecast=report.forecast.points if report.forecast else [],
        model_order=report.forecast.model_order if report.forecast else (0, 0, 0),
        metadata=metadata,
        current_cash=report.current_cash,
        average_monthly_flow=report.average_monthly_flow,
        csv_export=report.csv_export,
    )


@router.get("/budget-vs-actual", response_model=BudgetReportResponse)
def budget_vs_actual(
    budget_id: int = Query(..., ge=1),
    horizon: int | None = Query(default=None, ge=1),
    refresh: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> BudgetReportResponse:
    # TODO - Enforce organization scoping to prevent cross-tenant budget exposure.
    service = BudgetService(session)
    report = service.budget_vs_actual(budget_id, horizon=horizon, refresh=refresh)
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
    report = service.cashflow_forecast(organization_id, horizon=horizon, refresh=refresh)
    return _response_from_cashflow(report)
