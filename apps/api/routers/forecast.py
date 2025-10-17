"""Forecast related routes."""

from __future__ import annotations

from fastapi import APIRouter

from ..schemas import ForecastRequest, ForecastResponse
from ..services.forecast_service import ForecastService

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.post("/series", response_model=ForecastResponse)
def forecast_series(payload: ForecastRequest) -> ForecastResponse:
    """Generate a univariate time-series forecast."""

    fs = ForecastService()
    series = [(str(point[0]), float(point[1])) for point in payload.series]
    result = fs.forecast_series(series, payload.horizon)
    return ForecastResponse(forecast=result.points, horizon=result.horizon, order=result.model_order)
