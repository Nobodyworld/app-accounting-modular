"""Time-series forecasting utilities for Modular Accounting services."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Literal, Sequence

import pandas as pd
from pandas import DatetimeIndex, Series as PandasSeries
from pandas.api.types import DatetimeTZDtype
from statsmodels.tsa.arima.model import ARIMA, ARIMAResults


@dataclass(slots=True, frozen=True)
class ForecastResult:
    """Container for forecast outputs and diagnostics."""

    horizon: int
    points: list[tuple[str, float]]
    model_order: tuple[int, int, int]
    diagnostics: dict[str, float | int | str] | None = None
    timezone: str | None = None


class ForecastService:
    """ARIMA-backed forecaster with sensible defaults and fallbacks."""

    def __init__(
        self,
        candidate_orders: Iterable[tuple[int, int, int]] | None = None,
        *,
        minimum_observations: int = 8,
        fallback_strategy: Literal["repeat_last", "mean", "raise"] = "repeat_last",
    ):
        """Initialise the service with candidate orders and runtime safeguards.

        Args:
            candidate_orders: Optional iterable of ARIMA ``(p, d, q)`` orders.
            minimum_observations: Required observation count before fitting an ARIMA model.
            fallback_strategy: Behaviour when the series is shorter than ``minimum_observations``.
        """

        if minimum_observations < 1:
            raise ValueError("minimum_observations must be a positive integer")
        if fallback_strategy not in {"repeat_last", "mean", "raise"}:
            raise ValueError("Unsupported fallback strategy supplied")

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
        self.minimum_observations = minimum_observations
        self.fallback_strategy = fallback_strategy
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
                diagnostics={
                    "observations": 0,
                    "strategy": "empty_input",
                },
                timezone="UTC",
            )

        df, detected_timezone = self._prepare_series(series)

        if df.empty:
            raise ValueError("Series does not contain any numeric observations")

        if len(df.index) < self.minimum_observations:
            return self._fallback_response(df, horizon, detected_timezone)

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

        points = self._format_points(fc.index, fc.values, detected_timezone)
        diagnostics: dict[str, float | int | str] = {
            "observations": int(getattr(best_result, "nobs", len(df.index))),
            "aic": float(best_result.aic),
            "bic": float(best_result.bic),
            "hqic": float(getattr(best_result, "hqic", 0.0)),
            "model": "arima",
        }

        fitted_values = best_result.fittedvalues
        aligned_actuals = df["y"].reindex(fitted_values.index).dropna()
        residuals = aligned_actuals - fitted_values.reindex(aligned_actuals.index)
        if not residuals.empty:
            mae = float(residuals.abs().mean())
            rmse = float((residuals.pow(2).mean()) ** 0.5)
            diagnostics["mae"] = mae
            diagnostics["rmse"] = rmse
            diagnostics["residual_mean"] = float(residuals.mean())

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

    def _prepare_series(
        self, series: Sequence[tuple[object, float | int | Decimal]]
    ) -> tuple[pd.DataFrame, str | None]:
        """Normalise the incoming series and capture timezone metadata."""

        df = pd.DataFrame(series, columns=["ts", "y"]).copy()
        raw_ts = pd.to_datetime(df["ts"], utc=False, errors="coerce")
        detected_timezone = self._detect_timezone(raw_ts)

        df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
        df = df.dropna(subset=["ts"])
        if getattr(df["ts"].dt, "tz", None) is not None:
            df["ts"] = df["ts"].dt.tz_convert("UTC").dt.tz_localize(None)
        df = df.sort_values("ts").set_index("ts")
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

        return df, detected_timezone

    def _detect_timezone(self, timestamps: PandasSeries) -> str | None:
        """Detect timezone information from the raw timestamp series."""

        detected_timezone: str | None = None
        if isinstance(timestamps.dtype, DatetimeTZDtype):
            tzinfo = timestamps.dt.tz
            if tzinfo is not None:
                detected_timezone = getattr(tzinfo, "zone", None) or str(tzinfo)
            return detected_timezone

        tz_candidates: set[str] = set()
        for value in timestamps.dropna().tolist():
            tzinfo = getattr(value, "tzinfo", None)
            if tzinfo is not None:
                tz_name = getattr(tzinfo, "zone", None) or tzinfo.tzname(None)
                if tz_name:
                    tz_candidates.add(tz_name)
        if tz_candidates:
            detected_timezone = sorted(tz_candidates)[0]
        return detected_timezone

    def _fallback_response(
        self, df: pd.DataFrame, horizon: int, detected_timezone: str | None
    ) -> ForecastResult:
        """Produce a deterministic fallback forecast for short series."""

        if self.fallback_strategy == "raise":
            raise ValueError(
                "Insufficient observations to fit ARIMA model: "
                f"expected >= {self.minimum_observations}, received {len(df.index)}"
            )

        timezone = detected_timezone or "UTC"
        points: list[tuple[str, float]] = []
        diagnostics: dict[str, float | int | str] = {
            "observations": int(len(df.index)),
            "strategy": f"fallback_{self.fallback_strategy}",
        }
        if detected_timezone:
            diagnostics["source_timezone"] = detected_timezone

        if df.empty:
            diagnostics["detail"] = "Series had no numeric values"
            return ForecastResult(
                horizon=0,
                points=[],
                model_order=(0, 0, 0),
                diagnostics=diagnostics,
                timezone=timezone,
            )

        baseline_value: float
        if self.fallback_strategy == "mean":
            baseline_value = float(df["y"].mean())
        else:
            baseline_value = float(df["y"].iloc[-1])

        future_index = self._generate_future_index(df.index, horizon)
        formatted_index = self._convert_index_for_display(future_index, detected_timezone)
        points = [(ts.isoformat(), baseline_value) for ts in formatted_index]
        diagnostics["baseline_value"] = baseline_value
        last_observation = df.index[-1]
        last_observation_display = self._convert_index_for_display(
            DatetimeIndex([last_observation]), detected_timezone
        )
        if len(last_observation_display) == 1:
            last_observation_utc = last_observation_display.tz_convert("UTC")
            diagnostics["last_observation_epoch"] = float(
                last_observation_utc[0].timestamp()
            )
            diagnostics["last_observation_label"] = last_observation_display[0].isoformat()

        return ForecastResult(
            horizon=horizon,
            points=points,
            model_order=(0, 0, 0),
            diagnostics=diagnostics,
            timezone=timezone,
        )

    @staticmethod
    def _generate_future_index(index: DatetimeIndex, horizon: int) -> DatetimeIndex:
        """Generate a monotonic index for fallback forecasts."""

        if horizon <= 0:
            return DatetimeIndex([])

        if getattr(index, "freq", None) is not None:
            freq = index.freq
            return pd.date_range(start=index[-1] + freq, periods=horizon, freq=freq)

        if len(index) >= 2:
            step = index[-1] - index[-2]
            return DatetimeIndex([index[-1] + step * (i + 1) for i in range(horizon)])

        # With a single observation fall back to daily cadence.
        return DatetimeIndex([index[-1] + pd.Timedelta(days=i + 1) for i in range(horizon)])

    @staticmethod
    def _convert_index_for_display(
        index: DatetimeIndex, detected_timezone: str | None
    ) -> DatetimeIndex:
        """Normalise an index to UTC then convert to the detected timezone for output."""

        if index.empty:
            return index

        tz_aware = index
        if tz_aware.tz is None:
            tz_aware = tz_aware.tz_localize("UTC")

        if detected_timezone and detected_timezone != "UTC":
            try:
                tz_aware = tz_aware.tz_convert(detected_timezone)
            except Exception:
                # Fall back to UTC if pandas cannot resolve the timezone.
                tz_aware = tz_aware.tz_convert("UTC")
        return tz_aware

    def _format_points(
        self,
        index: Sequence[pd.Timestamp],
        values: Sequence[float],
        detected_timezone: str | None,
    ) -> list[tuple[str, float]]:
        """Produce ISO-8601 timestamps paired with forecast values."""

        display_index = self._convert_index_for_display(
            DatetimeIndex(index), detected_timezone
        )
        return [
            (ts.isoformat(), float(value))
            for ts, value in zip(display_index, values)
        ]
