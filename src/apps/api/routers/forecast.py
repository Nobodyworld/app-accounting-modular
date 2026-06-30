"""Forecast related routes."""

from __future__ import annotations

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


@router.post("/series", response_model=ForecastResponse)
def forecast_series(
    payload: ForecastRequest,
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ForecastResponse:
    """Generate a univariate time-series forecast."""

    get_current_organization(organization_id=payload.organization_id, session=s, current_user=current_user)
    if len(payload.series) < payload.horizon:
        raise HTTPException(status_code=400, detail="Series length must be at least the requested horizon")
    fs = _FORECAST_SERVICE
    # Pooled forecast service instance to reuse model state.
    series = [(str(point[0]), float(point[1])) for point in payload.series]
    regressors = payload.regressors or {}
    try:
        result = fs.forecast_series(series, payload.horizon, exogenous=regressors, model=payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    """Return registered forecasting models."""

    get_current_organization(organization_id=organization_id, session=s, current_user=current_user)
    models = []
    for item in _FORECAST_SERVICE.available_models():
        models.append(
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
        )
    return models


@router.post("/backtest", response_model=list[BacktestResponse])
def backtest_series(
    payload: BacktestRequest,
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[BacktestResponse]:
    """Run rolling backtests for the requested models."""

    get_current_organization(organization_id=payload.organization_id, session=s, current_user=current_user)
    try:
        results = _FORECAST_SERVICE.backtest(
            payload.series,
            horizon=payload.horizon,
            models=payload.models,
            exogenous=payload.regressors,
            initial_window=payload.initial_window,
            step=payload.step,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    """Estimate causal impact for a given intervention window."""

    get_current_organization(organization_id=payload.organization_id, session=s, current_user=current_user)
    try:
        result = _FORECAST_SERVICE.causal_impact(
            payload.series,
            event_start=payload.event_start,
            event_end=payload.event_end,
            interventions=payload.interventions,
            model=payload.model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
