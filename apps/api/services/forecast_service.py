from __future__ import annotations

import warnings
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence

import pandas as pd
from pandas import DatetimeIndex
from pandas.api.types import DatetimeTZDtype
from statsmodels.tsa.arima.model import ARIMA, ARIMAResults


@dataclass(slots=True, frozen=True)
class ForecastResult:
    """Container for forecast outputs and diagnostics."""

    horizon: int
    points: list[tuple[str, float]]
    model_order: tuple[int, int, int]
    diagnostics: dict[str, float | int] | None = None
    timezone: str | None = None


class ForecastService:
    def __init__(self, candidate_orders: Iterable[tuple[int, int, int]] | None = None):
        orders = (
            list(candidate_orders)
            if candidate_orders is not None
            else self._default_orders()
        )
        # Preserve order while removing duplicates.
        seen: set[tuple[int, int, int]] = set()
        deduped: list[tuple[int, int, int]] = []
        for order in orders:
            if order in seen:
                continue
            seen.add(order)
            deduped.append(order)
        self.candidate_orders = deduped
        # TODO - Allow pluggable model strategies beyond fixed ARIMA order search.

    def forecast_series(
        self, series: Sequence[tuple[object, float | int | Decimal]], horizon: int = 30
    ) -> ForecastResult:
        """Forecast a time series using the best ARIMA order by AIC."""

        if horizon <= 0:
            raise ValueError("Forecast horizon must be greater than zero")

        if not series:
            return ForecastResult(
                horizon=0,
                points=[],
                model_order=(0, 0, 0),
                diagnostics={"observations": 0},
                timezone="UTC",
            )

        df = pd.DataFrame(series, columns=["ts", "y"]).copy()
        # Preserve timezone context before coercing values to UTC to avoid
        # unintentional drift when series mix aware and naive timestamps.
        raw_ts = pd.to_datetime(df["ts"], utc=False, errors="coerce")
        detected_timezone: str | None = None
        if isinstance(raw_ts.dtype, DatetimeTZDtype):
            tzinfo = raw_ts.dt.tz
            if tzinfo is not None:
                detected_timezone = getattr(tzinfo, "zone", None) or str(tzinfo)
        else:
            tz_candidates: set[str] = set()
            for value in raw_ts.dropna().tolist():
                tzinfo = getattr(value, "tzinfo", None)
                if tzinfo is not None:
                    tz_name = getattr(tzinfo, "zone", None) or tzinfo.tzname(None)
                    if tz_name:
                        tz_candidates.add(tz_name)
            if tz_candidates:
                detected_timezone = sorted(tz_candidates)[0]

        df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
        df = df.dropna(subset=["ts"]).sort_values("ts")
        if getattr(df["ts"].dt, "tz", None) is not None:
            df["ts"] = df["ts"].dt.tz_convert("UTC").dt.tz_localize(None)
        df = df.set_index("ts")
        df = df[~df.index.duplicated(keep="last")]
        df["y"] = pd.to_numeric(df["y"], errors="coerce")
        df = df.dropna()

        if len(df.index) > 1:
            try:
                freq = pd.infer_freq(df.index)
            except ValueError:
                freq = None
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
                    warnings.simplefilter("ignore")
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

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fc = best_result.forecast(steps=horizon)
        points = [(str(idx), float(val)) for idx, val in fc.items()]
        diagnostics = {
            "observations": int(getattr(best_result, "nobs", len(df.index))),
            "aic": float(best_result.aic),
            "bic": float(best_result.bic),
            "hqic": float(getattr(best_result, "hqic", 0.0)),
        }
        if detected_timezone:
            diagnostics["source_timezone"] = detected_timezone

        return ForecastResult(
            horizon=horizon,
            points=points,
            model_order=best_order,
            diagnostics=diagnostics,
            timezone=detected_timezone or "UTC",
        )

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
