from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence

import warnings

import pandas as pd
from pandas import DatetimeIndex
from statsmodels.tsa.arima.model import ARIMA, ARIMAResults
from statsmodels.tools.sm_exceptions import ConvergenceWarning, ValueWarning


@dataclass(slots=True, frozen=True)
class ForecastResult:
    horizon: int
    points: list[tuple[str, float]]
    model_order: tuple[int, int, int]


class ForecastService:
    def __init__(self, candidate_orders: Iterable[tuple[int, int, int]] | None = None):
        orders = list(candidate_orders) if candidate_orders is not None else self._default_orders()
        # Preserve order while removing duplicates
        seen: set[tuple[int, int, int]] = set()
        self.candidate_orders = [o for o in orders if not (o in seen or seen.add(o))]

    def forecast_series(
        self, series: Sequence[tuple[object, float | int | Decimal]], horizon: int = 30
    ) -> ForecastResult:
        """Forecast a time series using the best ARIMA order by AIC."""

        if horizon <= 0:
            raise ValueError("Forecast horizon must be greater than zero")

        if not series:
            return ForecastResult(horizon=0, points=[], model_order=(0, 0, 0))

        df = pd.DataFrame(series, columns=["ts", "y"]).copy()
        df["ts"] = pd.to_datetime(df["ts"], utc=False, errors="coerce")
        df = df.dropna(subset=["ts"]).sort_values("ts").set_index("ts")
        df = df[~df.index.duplicated(keep="last")]
        df["y"] = pd.to_numeric(df["y"], errors="coerce")
        df = df.dropna()

        if len(df.index) > 1:
            freq = pd.infer_freq(df.index)
            if freq:
                df.index = DatetimeIndex(df.index, freq=freq)

        if df.empty:
            raise ValueError("Series does not contain any numeric observations")

        best_result: ARIMAResults | None = None
        best_order: tuple[int, int, int] | None = None
        best_aic: float | None = None

        for order in self.candidate_orders:
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=ConvergenceWarning)
                    warnings.filterwarnings("ignore", category=UserWarning)
                    warnings.filterwarnings("ignore", category=RuntimeWarning)
                    warnings.filterwarnings("ignore", category=FutureWarning)
                    warnings.filterwarnings("ignore", category=ValueWarning)
                    warnings.filterwarnings("ignore", category=DeprecationWarning)
                    model = ARIMA(df["y"], order=order)
                    result = model.fit()
            except Exception:  # statsmodels raises numerous specialised errors
                continue

            if best_aic is None or result.aic < best_aic:
                best_aic = result.aic
                best_result = result
                best_order = order

        if best_result is None or best_order is None:
            raise ValueError("Unable to fit ARIMA model with provided data")

        fc = best_result.forecast(steps=horizon)
        points = [(str(idx), float(val)) for idx, val in fc.items()]
        return ForecastResult(horizon=horizon, points=points, model_order=best_order)

    @staticmethod
    def _default_orders() -> list[tuple[int, int, int]]:
        return [
            (0, 0, 0),
            (1, 0, 0),
            (0, 1, 1),
            (1, 1, 0),
            (1, 1, 1),
            (2, 1, 1),
        ]
