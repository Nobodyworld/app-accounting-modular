"""Validated forecast boundary layered over the existing model engine."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
from pandas import DatetimeIndex

from . import forecast_legacy as _legacy

ARIMA = _legacy.ARIMA
BacktestFold = _legacy.BacktestFold
BacktestResult = _legacy.BacktestResult
CausalImpactResult = _legacy.CausalImpactResult
ForecastResult = _legacy.ForecastResult
ImpactPoint = _legacy.ImpactPoint
ModelInfo = _legacy.ModelInfo

__all__ = [
    "ARIMA",
    "BacktestFold",
    "BacktestResult",
    "CausalImpactResult",
    "ForecastResult",
    "ForecastService",
    "ImpactPoint",
    "ModelInfo",
]


class ForecastService(_legacy.ForecastService):
    """Forecast engine with deterministic validation and sanitized output contracts."""

    @staticmethod
    def _finite_float(value: object, label: str) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{label} must be numeric")
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{label} must be numeric") from exc
        if not math.isfinite(result):
            raise ValueError(f"{label} must be finite")
        return result

    @staticmethod
    def _timestamp(value: object, label: str) -> pd.Timestamp:
        try:
            result = pd.Timestamp(value)
        except Exception as exc:
            raise ValueError(f"{label} contains an invalid timestamp") from exc
        if pd.isna(result):
            raise ValueError(f"{label} contains an invalid timestamp")
        return result

    @staticmethod
    def _timezone_key(timestamp: pd.Timestamp) -> str:
        if timestamp.tzinfo is None:
            return "naive"
        return str(getattr(timestamp.tzinfo, "key", None) or timestamp.tzinfo)

    @staticmethod
    def _cadence_label(offset: pd.DateOffset, *, prefix: str | None = None) -> str:
        freq = str(getattr(offset, "freqstr", None) or offset)
        normalized = freq.lower()
        if normalized in {"d", "1d"}:
            label = "daily"
        elif normalized in {"h", "1h"}:
            label = "hourly"
        else:
            label = freq
        return f"{prefix}:{label}" if prefix else label

    @classmethod
    def _infer_cadence(cls, index: DatetimeIndex) -> tuple[pd.DateOffset, str]:
        if len(index) == 0:
            raise ValueError("Series must contain observations")
        if len(index) == 1:
            offset = pd.offsets.Day(1)
            return offset, "single-observation-daily-default"
        if len(index) == 2:
            delta = index[1] - index[0]
            if delta <= pd.Timedelta(0):
                raise ValueError("Series timestamps must increase")
            offset = pd.tseries.frequencies.to_offset(delta)
            return offset, cls._cadence_label(offset, prefix="two-point-observed-interval")
        inferred = pd.infer_freq(index)
        if inferred is None:
            raise ValueError("Series timestamps must use a regular cadence")
        offset = pd.tseries.frequencies.to_offset(inferred)
        return offset, cls._cadence_label(offset)

    def _prepare_frame(
        self,
        series: Sequence[tuple[str | date, float]],
        *,
        label: str,
        require_regular: bool,
    ) -> tuple[pd.DataFrame, str]:
        if not series:
            raise ValueError(f"{label} must contain observations")

        timezone_key: str | None = None
        aware: bool | None = None
        records: list[tuple[pd.Timestamp, float]] = []
        for timestamp_value, numeric_value in series:
            timestamp = self._timestamp(timestamp_value, label)
            timestamp_aware = timestamp.tzinfo is not None
            current_key = self._timezone_key(timestamp)
            if aware is None:
                aware = timestamp_aware
                timezone_key = current_key
            elif timestamp_aware != aware:
                raise ValueError(f"{label} timestamps cannot mix naive and timezone-aware values")
            elif current_key != timezone_key:
                raise ValueError(f"{label} timestamps must use one timezone")
            records.append((timestamp, self._finite_float(numeric_value, f"{label} values")))

        deduplicated: dict[pd.Timestamp, float] = {}
        for timestamp, value in records:
            deduplicated[timestamp] = value
        ordered = sorted(deduplicated.items(), key=lambda item: item[0])
        index = pd.DatetimeIndex([item[0] for item in ordered])
        cadence = "not-evaluated"
        if require_regular:
            offset, cadence = self._infer_cadence(index)
            try:
                index = pd.DatetimeIndex(index, freq=offset)
            except ValueError as exc:
                raise ValueError(f"{label} timestamps must use a regular cadence") from exc

        frame = pd.DataFrame({"y": [item[1] for item in ordered]}, index=index)
        frame.attrs["cadence"] = cadence
        frame.attrs["duplicates_resolved"] = len(records) - len(ordered)
        frame.attrs["timezone_key"] = timezone_key or "naive"
        timezone = "UTC" if timezone_key in (None, "naive") else timezone_key
        return frame, timezone

    def _prepare_series(self, series: list[tuple[str | date, float]]) -> tuple[pd.DataFrame, str | None]:
        return self._prepare_frame(series, label="Series", require_regular=True)

    def _generate_future_index(self, index: DatetimeIndex, horizon: int) -> DatetimeIndex:
        if horizon <= 0:
            raise ValueError("horizon must be positive")
        offset = index.freq
        if offset is None:
            offset, _ = self._infer_cadence(index)
        return pd.date_range(start=index[-1], periods=horizon + 1, freq=offset)[1:]

    def _prepare_exogenous(
        self,
        df: pd.DataFrame,
        exogenous: Mapping[str, Sequence[tuple[str | date, float]]],
    ) -> pd.DataFrame:
        base_index = pd.DatetimeIndex(df.index)
        target_timezone = str(df.attrs.get("timezone_key", self._timezone_key(pd.Timestamp(base_index[0]))))
        aligned_frame = pd.DataFrame(index=base_index)
        seen: set[str] = set()

        for raw_name in sorted(exogenous):
            name = raw_name.strip()
            if not name:
                raise ValueError("Regressor names must not be empty")
            if name in seen:
                raise ValueError(f"Regressor names must be unique: {name}")
            seen.add(name)
            values = exogenous[raw_name]
            frame, _ = self._prepare_frame(values, label=f"Regressor '{name}'", require_regular=False)
            regressor_timezone = str(frame.attrs.get("timezone_key"))
            if regressor_timezone != target_timezone:
                raise ValueError(f"Regressor '{name}' must use the target series timezone")
            regressor_index = pd.DatetimeIndex(frame.index)
            outside = regressor_index.difference(base_index)
            if len(outside):
                raise ValueError(f"Regressor '{name}' timestamps must align with the target series")
            aligned = frame["y"].reindex(base_index, method="ffill")
            if aligned.isna().any():
                raise ValueError(f"Regressor '{name}' must begin at the first target timestamp")
            values_array = aligned.to_numpy(dtype=float)
            if not np.isfinite(values_array).all():
                raise ValueError(f"Regressor '{name}' values must be finite")
            aligned_frame[name] = values_array

        return aligned_frame

    def _default_future_exog(self, exog_df: pd.DataFrame, forecast_index: DatetimeIndex) -> pd.DataFrame:
        if exog_df.empty:
            raise ValueError("Regressor history must contain observations")
        values = exog_df.to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("Regressor values must be finite")
        last_values = exog_df.iloc[-1].to_dict()
        result = pd.DataFrame([last_values for _ in forecast_index], index=forecast_index)
        if not np.isfinite(result.to_numpy(dtype=float)).all():
            raise ValueError("Future regressor values must be finite")
        return result

    @classmethod
    def _validate_diagnostic_value(cls, value: object, *, depth: int = 0) -> None:
        if depth > 8:
            raise ValueError("Forecast diagnostics exceed the supported nesting depth")
        if value is None or isinstance(value, str | bool):
            return
        if isinstance(value, (int, float, np.integer, np.floating)):
            cls._finite_float(value, "Forecast diagnostics")
            return
        if isinstance(value, Mapping):
            if len(value) > 256:
                raise ValueError("Forecast diagnostics contain too many fields")
            for key, nested in value.items():
                if not isinstance(key, str):
                    raise ValueError("Forecast diagnostic keys must be strings")
                cls._validate_diagnostic_value(nested, depth=depth + 1)
            return
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            if len(value) > 256:
                raise ValueError("Forecast diagnostics contain too many values")
            for nested in value:
                cls._validate_diagnostic_value(nested, depth=depth + 1)
            return
        raise ValueError("Forecast diagnostics contain an unsupported value")

    def _validate_forecast_result(self, result: ForecastResult) -> ForecastResult:
        if result.horizon != len(result.points):
            raise ValueError("Forecast model returned an unexpected number of points")
        previous: pd.Timestamp | None = None
        for timestamp_text, value in result.points:
            timestamp = self._timestamp(timestamp_text, "Forecast output")
            if previous is not None and timestamp <= previous:
                raise ValueError("Forecast output timestamps must increase")
            previous = timestamp
            self._finite_float(value, "Forecast output values")
        if result.diagnostics is not None:
            self._validate_diagnostic_value(result.diagnostics)
        return result

    @staticmethod
    def _copy_diagnostics(result: ForecastResult) -> dict[str, object]:
        return dict(result.diagnostics or {})

    def _augment_result(self, result: ForecastResult, df: pd.DataFrame) -> ForecastResult:
        diagnostics = self._copy_diagnostics(result)
        diagnostics["cadence"] = str(df.attrs.get("cadence", "unknown"))
        diagnostics["duplicate_timestamps_resolved"] = int(df.attrs.get("duplicates_resolved", 0))
        result.diagnostics = diagnostics
        return self._validate_forecast_result(result)

    def _fallback(
        self,
        df: pd.DataFrame,
        horizon: int,
        timezone: str | None,
        *,
        model: str,
    ) -> ForecastResult:
        return self._augment_result(super()._fallback(df, horizon, timezone, model=model), df)

    def _dispatch_model(
        self,
        model: str,
        df: pd.DataFrame,
        horizon: int,
        timezone: str | None,
        *,
        exog_df: pd.DataFrame | None,
        exog_future: pd.DataFrame | None,
    ) -> ForecastResult:
        _legacy.ARIMA = ARIMA
        result = super()._dispatch_model(
            model,
            df,
            horizon,
            timezone,
            exog_df=exog_df,
            exog_future=exog_future,
        )
        return self._augment_result(result, df)

    def forecast_series(
        self,
        series: Sequence[tuple[str | date, float]],
        horizon: int = 30,
        *,
        exogenous: Mapping[str, Sequence[tuple[str | date, float]]] | None = None,
        model: str = "arima",
    ) -> ForecastResult:
        if horizon <= 0:
            raise ValueError("horizon must be positive")
        if not series:
            result = super().forecast_series(series, horizon, exogenous=exogenous, model=model)
            return self._validate_forecast_result(result)
        df, _ = self._prepare_series(list(series))
        result = super().forecast_series(series, horizon, exogenous=exogenous, model=model)
        return self._augment_result(result, df)

    @classmethod
    def _validated_metric_inputs(
        cls,
        actual: Sequence[float],
        predicted: Sequence[float],
    ) -> tuple[list[float], list[float]]:
        if len(actual) != len(predicted) or not actual:
            raise ValueError("Forecast metric inputs must be nonempty and equal in length")
        actual_values = [cls._finite_float(value, "Actual values") for value in actual]
        predicted_values = [cls._finite_float(value, "Predicted values") for value in predicted]
        return actual_values, predicted_values

    @classmethod
    def _metric_mae(cls, actual: Sequence[float], predicted: Sequence[float]) -> float:
        actual_values, predicted_values = cls._validated_metric_inputs(actual, predicted)
        return cls._finite_float(
            np.mean(np.abs(np.subtract(actual_values, predicted_values))),
            "MAE",
        )

    @classmethod
    def _metric_rmse(cls, actual: Sequence[float], predicted: Sequence[float]) -> float:
        actual_values, predicted_values = cls._validated_metric_inputs(actual, predicted)
        return cls._finite_float(
            np.sqrt(np.mean(np.square(np.subtract(actual_values, predicted_values)))),
            "RMSE",
        )

    @classmethod
    def _metric_mape(cls, actual: Sequence[float], predicted: Sequence[float]) -> float | None:
        actual_values, predicted_values = cls._validated_metric_inputs(actual, predicted)
        if any(value == 0 for value in actual_values):
            return None
        return cls._finite_float(
            np.mean(
                np.abs(
                    (np.asarray(actual_values, dtype=float) - np.asarray(predicted_values, dtype=float))
                    / np.asarray(actual_values, dtype=float)
                )
            )
            * 100,
            "MAPE",
        )

    def backtest(
        self,
        series: Sequence[tuple[str | date, float]],
        horizon: int = 7,
        *,
        models: Sequence[str] | None = None,
        exogenous: Mapping[str, Sequence[tuple[str | date, float]]] | None = None,
        initial_window: int | None = None,
        step: int | None = None,
    ) -> list[BacktestResult]:
        if initial_window is not None and initial_window <= 0:
            raise ValueError("initial_window must be positive")
        if step is not None and step <= 0:
            raise ValueError("step must be positive")
        results = super().backtest(
            series,
            horizon,
            models=models,
            exogenous=exogenous,
            initial_window=initial_window,
            step=step,
        )
        for result in results:
            for fold in result.folds:
                if fold.horizon != len(fold.actual) or fold.horizon != len(fold.forecast):
                    raise ValueError("Backtest fold returned an unexpected number of points")
                self._finite_float(fold.mae, "Backtest MAE")
                self._finite_float(fold.rmse, "Backtest RMSE")
                if fold.mape is not None:
                    self._finite_float(fold.mape, "Backtest MAPE")
                for _, value in fold.actual:
                    self._finite_float(value, "Backtest actual values")
                for _, value in fold.forecast:
                    self._finite_float(value, "Backtest forecast values")
            for name, value in result.metrics.items():
                if value is not None:
                    self._finite_float(value, f"Backtest metric '{name}'")
        return results

    def _event_timestamp(self, value: object, *, label: str, target_timezone: str) -> pd.Timestamp:
        timestamp = self._timestamp(value, label)
        timezone = self._timezone_key(timestamp)
        if timezone != target_timezone:
            if {timezone, target_timezone} == {"naive", "UTC"}:
                return timestamp
            raise ValueError(f"{label} must use the target series timezone")
        return timestamp

    def causal_impact(
        self,
        series: Sequence[tuple[str | date, float]],
        event_start: str | date | datetime,
        *,
        event_end: str | date | datetime | None = None,
        interventions: Mapping[str, Sequence[tuple[str | date, float]]] | None = None,
        model: str = "arima",
    ) -> CausalImpactResult:
        df, _ = self._prepare_series(list(series))
        target_timezone = str(df.attrs.get("timezone_key", "naive"))
        start = self._event_timestamp(event_start, label="event_start", target_timezone=target_timezone)
        end = (
            self._event_timestamp(event_end, label="event_end", target_timezone=target_timezone)
            if event_end is not None
            else pd.Timestamp(df.index[-1])
        )
        if end < start:
            raise ValueError("event_end must not precede event_start")
        if start < df.index[0] or start > df.index[-1] or end > df.index[-1]:
            raise ValueError("Event window must be contained within the target series")

        result = super().causal_impact(
            series,
            event_start=start,
            event_end=end,
            interventions=interventions,
            model=model,
        )
        self._finite_float(result.average_impact, "Average impact")
        self._finite_float(result.cumulative_impact, "Cumulative impact")
        if result.p_value is not None:
            p_value = self._finite_float(result.p_value, "Impact p-value")
            if not 0 <= p_value <= 1:
                raise ValueError("Impact p-value must be between 0 and 1")
        for point in result.points:
            self._finite_float(point.actual, "Impact actual values")
            self._finite_float(point.predicted, "Impact predicted values")
            self._finite_float(point.impact, "Impact values")
        self._validate_diagnostic_value(result.diagnostics)
        result.diagnostics["cadence"] = str(df.attrs.get("cadence", "unknown"))
        result.diagnostics["duplicate_timestamps_resolved"] = int(df.attrs.get("duplicates_resolved", 0))
        return result
