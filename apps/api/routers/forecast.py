from fastapi import APIRouter
from ..services.forecast_service import ForecastService

router = APIRouter(prefix="/forecast", tags=["forecast"])

@router.post("/series")
def forecast_series(payload: dict):
    series = payload.get("series", [])
    horizon = int(payload.get("horizon", 30))
    fs = ForecastService()
    return {"forecast": fs.forecast_series(series, horizon)}
