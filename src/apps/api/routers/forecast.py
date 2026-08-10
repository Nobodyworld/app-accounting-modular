"""Forecast-related routes with tenant-first authorization and sanitized failures."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..models.models import User
from ..schemas import (
    BacktestFoldSchema,
    BacktestRequest,
    BacktestResponse,
    CausalImpactRequest,
    CausalImpactResponse,
    ForecastModelInfo,
    ForecastRequest,
    ForecastResponse,
    ImpactPointSchema,
)
from ..security import get_current_organization, get_current_user
from ..services.forecast_service import ForecastService

router = APIRouter(prefix="/forecast", tags=["forecast"])
_FORECAST_SERVICE = ForecastService()
logger = logging.getLogger(__name__)

_ResultT = TypeVar("_ResultT")
_SAFE_VALIDATION_PREFIXES = (
    "Actual values",
    "Average impact",
    "Backtest ",
    "Event window",
    "Forecast ",
    "Impact ",
    "Insufficient ",
    "MAE",
    "MAPE",
    "Model dependency",
    "Not enough ",
    "Predicted values",
    "RMSE",
    "Regressor ",
    "Regressor names",
    "Series ",
    "Unsupported forecasting model",
    "event_end",
    "event_start",
    "horizon",
    "initial_window",
    "scikit-learn is required",
    "step",
    "Prophet model requested",
)


def _safe_validation_detail(exc: ValueError) -> str:
    detail = str(exc).strip()
    if detail and len(detail) <= 240 and detail.startswith(_SAFE_VALIDATION_PREFIXES):
        return detail
    return "Forecast request could not be evaluated"


def _execute_forecast(operation: str, action: Callable[[], _ResultT]) -> _ResultT:
    try:
        return action()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_safe_validation_detail(exc)) from None
    except Exception as exc:
        logger.warning(
            "Forecast operation failed",
            extra={"operation": operation, "error_type": type(exc).__name__},
        )
        raise HTTPException(status_code=400, detail="Forecast operation could not be completed") from None


@router.post("/series", response_model=ForecastResponse)
def forecast_series(
    payload: ForecastRequest,
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ForecastResponse:
    """Generate a bounded time-series forecast for an authorized organization."""

    get_current_organization(organization_id=payload.organization_id, session=s, current_user=current_user)
    if len(payload.series) < payload.horizon:
        raise HTTPException(status_code=400, detail="Series length must be at least the requested horizon")

    series = [(str(point[0]), float(point[1])) for point in payload.series]
    regressors = payload.regressors or {}
    result = _execute_forecast(
        "series",
        lambda: _FORECAST_SERVICE.forecast_series(
            series,
            payload.horizon,
            exogenous=regressors,
            model=payload.model,
        ),
    )
    return ForecastResponse(
        forecast=result.points,
        horizon=result.horizon,
        order=result.model_order,
        diagnostics=result.diagnostics,
        model=result.model,
        timezone=result.timezone,
    )


@router.get("/models", response_model=list[ForecastModelInfo])
def list_models(
    organization_id: int,
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ForecastModelInfo]:
    """Return registered forecasting models after tenant authorization."""

    get_current_organization(organization_id=organization_id, session=s, current_user=current_user)
    model_info = _execute_forecast("models", _FORECAST_SERVICE.available_models)
    return [
        ForecastModelInfo(
            key=item.key,
            name=item.name,
            family=item.family,
            description=item.description,
            supports_exogenous=item.supports_exogenous,
            available=item.available,
            requirements=item.requirements,
            notes=item.notes,
        )
        for item in model_info
    ]


@router.post("/backtest", response_model=list[BacktestResponse])
def backtest_series(
    payload: BacktestRequest,
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[BacktestResponse]:
    """Run rolling backtests for an authorized organization."""

    get_current_organization(organization_id=payload.organization_id, session=s, current_user=current_user)
    results = _execute_forecast(
        "backtest",
        lambda: _FORECAST_SERVICE.backtest(
            payload.series,
            horizon=payload.horizon,
            models=payload.models,
            exogenous=payload.regressors,
            initial_window=payload.initial_window,
            step=payload.step,
        ),
    )
    return [
        BacktestResponse(
            model=result.model,
            folds=[
                BacktestFoldSchema(
                    start=fold.start,
                    end=fold.end,
                    horizon=fold.horizon,
                    actual=fold.actual,
                    forecast=fold.forecast,
                    mae=fold.mae,
                    rmse=fold.rmse,
                    mape=fold.mape,
                )
                for fold in result.folds
            ],
            metrics=result.metrics,
            tested_points=result.tested_points,
            available=result.available,
            reason=result.reason,
            timezone=result.timezone,
        )
        for result in results
    ]


@router.post("/impact", response_model=CausalImpactResponse)
def causal_impact(
    payload: CausalImpactRequest,
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CausalImpactResponse:
    """Estimate a bounded causal-impact window for an authorized organization."""

    get_current_organization(organization_id=payload.organization_id, session=s, current_user=current_user)
    result = _execute_forecast(
        "impact",
        lambda: _FORECAST_SERVICE.causal_impact(
            payload.series,
            event_start=payload.event_start,
            event_end=payload.event_end,
            interventions=payload.interventions,
            model=payload.model,
        ),
    )
    return CausalImpactResponse(
        model=result.model,
        event_start=result.event_start,
        event_end=result.event_end,
        average_impact=result.average_impact,
        cumulative_impact=result.cumulative_impact,
        p_value=result.p_value,
        points=[
            ImpactPointSchema(
                timestamp=point.timestamp,
                actual=point.actual,
                predicted=point.predicted,
                impact=point.impact,
            )
            for point in result.points
        ],
        diagnostics=result.diagnostics,
        timezone=result.timezone,
    )
