from typing import Sequence, List, Tuple
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
import logging

logger = logging.getLogger(__name__)

class ForecastService:
    def forecast_series(self, series: Sequence[Tuple[str, float]], horizon: int = 30) -> List[Tuple[str, float]]:
        """Forecast time series using ARIMA model."""
        if not series:
            return []
        try:
            df = pd.DataFrame(series, columns=["ts","y"]).copy()
            df["ts"] = pd.to_datetime(df["ts"])
            df = df.sort_values("ts").set_index("ts")
            # Simple ARIMA(1,1,1) baseline; # TODO auto-order selection & exogenous features
            model = ARIMA(df["y"], order=(1,1,1))
            res = model.fit()
            fc = res.forecast(steps=horizon)
            out = [(str(idx), float(val)) for idx, val in fc.items()]
            return out
        except Exception as e:
            logger.error(f"Forecast failed: {e}")
            raise
