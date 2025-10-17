from fastapi import APIRouter, HTTPException, status

from ..schemas import ForecastRequest, ForecastResponse
from ..services.forecast_service import ForecastService

router = APIRouter(prefix="/forecast", tags=["forecast"])

@router.post("/series", response_model=ForecastResponse, status_code=status.HTTP_200_OK)
def forecast_series(payload: ForecastRequest) -> ForecastResponse:
    service = ForecastService()
    series = [(point.timestamp, point.value) for point in payload.series]
    try:
        result = service.forecast_series(series, horizon=payload.horizon)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ForecastResponse(forecast=result.points, horizon=result.horizon, order=result.model_order)
