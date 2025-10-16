from typing import Sequence
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

class ForecastService:
    def forecast_series(self, series: Sequence[tuple], horizon: int = 30):
        # series: [(ts, value), ...] ts can be str or datetime-like
        if not series:
            return []
        df = pd.DataFrame(series, columns=["ts","y"]).copy()
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.sort_values("ts").set_index("ts")
        # Simple ARIMA(1,1,1) baseline; # TODO auto-order selection & exogenous features
        model = ARIMA(df["y"], order=(1,1,1))
        res = model.fit()
        fc = res.forecast(steps=horizon)
        out = [(str(idx), float(val)) for idx, val in fc.items()]
        return out
