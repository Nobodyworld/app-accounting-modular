"""Forecast related routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..db import get_session
from ..models.models import User
from ..schemas import ForecastRequest, ForecastResponse
from ..security import get_current_organization, get_current_user
from ..services.forecast_service import ForecastService

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.post("/series", response_model=ForecastResponse)
def forecast_series(
    payload: ForecastRequest,
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ForecastResponse:
    """Generate a univariate time-series forecast."""

    get_current_organization(
        organization_id=payload.organization_id, session=s, current_user=current_user
    )
    fs = ForecastService()
    # TODO - Pool forecast service instances to reuse expensive model state.
    series = [(str(point[0]), float(point[1])) for point in payload.series]
    # TODO - Validate series length against horizon to prevent underfit models.
    result = fs.forecast_series(series, payload.horizon)
    return ForecastResponse(
        forecast=result.points, horizon=result.horizon, order=result.model_order
    )
