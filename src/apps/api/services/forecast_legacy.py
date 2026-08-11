from __future__ import annotations

import importlib
import logging
import math
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from math import sqrt
from typing import Any, Literal, cast

import numpy as np
import pandas as pd
from pandas import DatetimeIndex
from statsmodels.tsa.arima.model import ARIMA

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ForecastResult:
    """Structured forecast output including diagnostics."""

    horizon: int
    points: list[tuple[str, float]]
    model_order: tuple[int, int, int]
    diagnostics: dict[str, object] | None
    timezone: str | None
    model: str = "arima"


@dataclass(slots=True)
class ModelInfo:
    """Model registry metadata exposed via the API."""

    key: str
    name: str
    family: Literal["statistical", "bayesian", "ml"]
    description: str
    supports_exogenous: bool = False
    available: bool = True
    requirements: tuple[str, ...] = ()
    notes: str | None = None


@dataclass(slots=True)
class BacktestFold:
    """Single rolling-origin evaluation fold."""

    start: str
    end: str
    horizon: int
    actual: list[tuple[str, float]]
    forecast: list[tuple[str, float]]
    mae: float
    rmse: float
    mape: float | None


@dataclass(slots=True)
class BacktestResult:
    """Aggregated metrics for a model across folds."""

    model: str
    folds: list[BacktestFold]
    metrics: dict[str, float | None]
    tested_points: int
    available: bool = True
    reason: str | None = None
    timezone: str | None = None


@dataclass(slots=True)
class ImpactPoint:
    """Counterfactual vs observed for a single timestamp."""

    timestamp: str
    actual: float
    predicted: float
    impact: float


@dataclass(slots=True)
class CausalImpactResult:
    """Summary of a causal impact analysis run."""

    model: str
    event_start: str
    event_end: str
    average_impact: float
    cumulative_impact: float
    p_value: float | None
    points: list[ImpactPoint]
    diagnostics: dict[str, object]
    timezone: str | None = None


class ForecastService:
    def __init__(
        self,
        *,
        candidate_orders: list[tuple[int, int, int]] | None = None,
        minimum_observations: int = 5,
        fallback_strategy: Literal["repeat_last", "mean", "raise"] = "repeat_last",
    ):
        if minimum_observations < 1:
            raise ValueError("minimum_observations must be at least 1")
        if fallback_strategy not in ("repeat_last", "mean", "raise"):
            raise ValueError("Unsupported fallback strategy")

        self.candidate_orders = candidate_orders or [
            (1, 1, 1),
            (0, 1, 1),
            (1, 1, 0),
            (2, 1, 1),
            (1, 0, 1),
        ]
        self.minimum_observations = minimum_observations
        self.fallback_strategy = fallback_strategy
        self._prophet_class: Any | None = None
        self._prophet_error: Exception | None = None
        self._sklearn_error: Exception | None = None
        self._model_registry = self._build_registry()

    # ------------------------------------------------------------------
    # Model registry helpers
    # ------------------------------------------------------------------
    def _build_registry(self) -> dict[str, ModelInfo]:
        return {
            "arima": ModelInfo(
                key="arima",
                name="Auto ARIMA",
                family="statistical",
                description="Seasonal-friendly ARIMA with optional exogenous regressors",
                supports_exogenous=True,
                available=True,
            ),
            "prophet": ModelInfo(
                key="prophet",
                name="Prophet",
                family="bayesian",
                description="Prophet with automatic seasonality and custom regressors",
                supports_exogenous=True,
                available=self._prophet_available(),
                requirements=("prophet>=1.0",),
                notes="Install the optional 'prophet' dependency to enable.",
            ),
            "gradient_boosting": ModelInfo(
                key="gradient_boosting",
                name="Gradient Boosting Regressor",
                family="ml",
                description="Tree-based regressor with lagged features and seasonality signals",
                supports_exogenous=True,
                available=self._sklearn_available(),
                requirements=("scikit-learn>=1.5",),
            ),
        }

    def available_models(self) -> list[ModelInfo]:
        """Return registered models with availability state."""

        models = list(self._model_registry.values())
        models.sort(key=lambda item: item.key)
        return models

    def _normalise_model_key(self, model: str) -> str:
        key = (model or "arima").strip().lower()
        aliases = {
            "fbprophet": "prophet",
            "ml": "gradient_boosting",
            "gbr": "gradient_boosting",
            "gboost": "gradient_boosting",
            "boosting": "gradient_boosting",
        }
        return aliases.get(key, key)

    def _prophet_available(self) -> bool:
        if self._prophet_class is not None:
            return True
        try:
            module = importlib.import_module("prophet")
            self._prophet_class = module.Prophet
            return True
        except Exception as exc:  # pragma: no cover - availability depends on environment
            self._prophet_error = exc
            logger.debug("Prophet unavailable: %s", exc)
            return False

    def _sklearn_available(self) -> bool:
        try:
            importlib.import_module("sklearn")
            return True
        except Exception as exc:  # pragma: no cover - availability depends on environment
            self._sklearn_error = exc
            logger.debug("scikit-learn unavailable: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------
    def _prepare_series(self, series: list[tuple[str | date, float]]) -> tuple[pd.DataFrame, str | None]:
        df = pd.DataFrame(series, columns=["ts", "y"]).copy()
        try:
            df["y"] = pd.to_numeric(df["y"], errors="raise").astype(float)
        except Exception as exc:
            raise ValueError("Series contains non-numeric values") from exc

        df["ts"] = pd.to_datetime(df["ts"])
        df = df.drop_duplicates(subset="ts", keep="last").sort_values("ts")
        timezone = None
        if df["ts"].dt.tz is None:
            timezone = "UTC"
        else:
            timezone = str(df["ts"].dt.tz)
        df = df.set_index("ts")
        return df, timezone

    def _generate_future_index(self, index: DatetimeIndex, horizon: int) -> DatetimeIndex:
        if index.freq is not None:
            start = index[-1] + index.freq
            return pd.date_range(start=start, periods=horizon, freq=index.freq)

        if len(index) >= 2:
            inferred = pd.tseries.frequencies.to_offset(index[-1] - index[-2])
        else:
            inferred = pd.offsets.Day(1)
        start = index[-1] + inferred
        return pd.date_range(start=start, periods=horizon, freq=inferred)

    def _fallback(
        self,
        df: pd.DataFrame,
        horizon: int,
        timezone: str | None,
        *,
        model: str,
    ) -> ForecastResult:
        if self.fallback_strategy == "raise":
            raise ValueError("Insufficient observations for forecasting")

        future_index = self._generate_future_index(pd.DatetimeIndex(df.index), horizon)
        diagnostics: dict[str, object] = {"observations": len(df), "model": model}

        if self.fallback_strategy == "mean":
            value = float(df["y"].mean())
            diagnostics["strategy"] = "fallback_mean"
        else:
            value = float(df["y"].iloc[-1])
            diagnostics["strategy"] = "fallback_repeat_last"
            last = df.index[-1]
            ts = pd.Timestamp(last)
            ts_utc = ts.tz_convert("UTC") if ts.tzinfo is not None else ts.tz_localize("UTC")
            diagnostics["last_observation_label"] = ts.isoformat() if ts.tzinfo is not None else ts_utc.isoformat()
            diagnostics["last_observation_epoch"] = ts_utc.timestamp()

        if timezone and timezone != "UTC":
            diagnostics["source_timezone"] = timezone

        points = [(stamp.isoformat(), value) for stamp in future_index]
        return ForecastResult(
            horizon=horizon,
            points=points,
            model_order=(0, 0, 0),
            diagnostics=diagnostics,
            timezone=timezone or "UTC",
            model=model,
        )

    def _prepare_exogenous(
        self, df: pd.DataFrame, exogenous: Mapping[str, Sequence[tuple[str | date, float]]]
    ) -> pd.DataFrame:
        """Align exogenous regressors with the target series index."""

        base_index = df.index
        exog_df = pd.DataFrame(index=base_index)
        for name, values in exogenous.items():
            series_df = pd.DataFrame(values, columns=["ts", name])
            series_df["ts"] = pd.to_datetime(series_df["ts"])
            series_df = series_df.drop_duplicates(subset="ts", keep="last").set_index("ts").sort_index()
            aligned = series_df.reindex(base_index, method="ffill").fillna(0.0)
            exog_df[name] = pd.to_numeric(aligned[name], errors="coerce").fillna(0.0)
        return exog_df

    def _default_future_exog(self, exog_df: pd.DataFrame, forecast_index: DatetimeIndex) -> pd.DataFrame:
        last_row = exog_df.iloc[-1:]
        exog_future = pd.concat([last_row] * len(forecast_index), ignore_index=True)
        exog_future.index = forecast_index
        return exog_future

    def build_event_regressors(
        self,
        events: Sequence[tuple[str | date, str]],
        *,
        keywords: Sequence[str] | None = None,
    ) -> dict[str, list[tuple[str, float]]]:
        """Convert event text into simple numeric regressors.

        Counts keyword occurrences per event timestamp to produce a dummy series
        suitable for the ``exogenous`` argument.
        """

        vocab = {kw.lower() for kw in (keywords or ("tax", "supply", "demand", "regulation", "outage"))}
        series: list[tuple[str, float]] = []
        for ts, text in events:
            tokens = text.lower().split()
            score = float(sum(1 for token in tokens if token.strip(".,;!") in vocab))
            ts_label = pd.to_datetime(ts).isoformat()
            series.append((ts_label, score))
        return {"event_intensity": series}

    # ------------------------------------------------------------------
    # Forecasting entrypoints
    # ------------------------------------------------------------------
    def forecast_series(
        self,
        series: Sequence[tuple[str | date, float]],
        horizon: int = 30,
        *,
        exogenous: Mapping[str, Sequence[tuple[str | date, float]]] | None = None,
        model: str = "arima",
    ) -> ForecastResult:
        """Forecast time series using the requested model with sensible fallbacks."""

        if horizon <= 0:
            raise ValueError("horizon must be positive")
        if not series:
            return ForecastResult(
                horizon=0,
                points=[],
                model_order=(0, 0, 0),
                diagnostics={"observations": 0, "strategy": "empty_input", "model": model},
                timezone="UTC",
                model=model,
            )

        df, timezone = self._prepare_series(list(series))
        model_key = self._normalise_model_key(model)
        exog_df = self._prepare_exogenous(df, exogenous) if exogenous else None
        if len(df) < self.minimum_observations:
            return self._fallback(df, horizon, timezone, model=model_key)

        return self._dispatch_model(
            model_key,
            df,
            horizon,
            timezone,
            exog_df=exog_df,
            exog_future=None,
        )

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
        if model == "arima":
            return self._forecast_arima(df, horizon, timezone, exog_df=exog_df, exog_future=exog_future)
        if model == "prophet":
            return self._forecast_prophet(df, horizon, timezone, exog_df=exog_df, exog_future=exog_future)
        if model == "gradient_boosting":
            return self._forecast_gradient_boosting(df, horizon, timezone, exog_df=exog_df, exog_future=exog_future)
        raise ValueError(f"Unsupported forecasting model '{model}'")

    def _forecast_arima(
        self,
        df: pd.DataFrame,
        horizon: int,
        timezone: str | None,
        *,
        exog_df: pd.DataFrame | None,
        exog_future: pd.DataFrame | None,
    ) -> ForecastResult:
        best = None
        best_order: tuple[int, int, int] | None = None
        for order in self.candidate_orders:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model = ARIMA(df["y"], order=order, exog=exog_df)
                    res = model.fit()
            except Exception:
                continue

            score = res.aic + res.bic if hasattr(res, "bic") else res.aic
            if best is None or score < (best.aic + getattr(best, "bic", best.aic)):
                best = res
                best_order = order

        if best is None or best_order is None:
            return self._fallback(df, horizon, timezone, model="arima")

        forecast_index = self._generate_future_index(pd.DatetimeIndex(df.index), horizon)
        effective_exog_future = None
        if exog_df is not None:
            effective_exog_future = exog_future or self._default_future_exog(exog_df, forecast_index)
        forecast_values = best.forecast(steps=horizon, exog=effective_exog_future)
        points = [
            (stamp.isoformat(), float(value)) for stamp, value in zip(forecast_index, forecast_values, strict=False)
        ]

        residuals = best.resid.dropna()
        mae = float(abs(residuals).mean()) if not residuals.empty else 0.0
        rmse = float(sqrt((residuals**2).mean())) if not residuals.empty else 0.0
        diagnostics: dict[str, object] = {
            "observations": len(df),
            "model": "arima",
            "mae": mae,
            "rmse": rmse,
        }
        if timezone and timezone != "UTC":
            diagnostics["source_timezone"] = timezone

        return ForecastResult(
            horizon=horizon,
            points=points,
            model_order=best_order,
            diagnostics=diagnostics,
            timezone=timezone or "UTC",
            model="arima",
        )

    def _forecast_prophet(
        self,
        df: pd.DataFrame,
        horizon: int,
        timezone: str | None,
        *,
        exog_df: pd.DataFrame | None,
        exog_future: pd.DataFrame | None,
    ) -> ForecastResult:
        if not self._prophet_available():
            msg = "Prophet model requested but dependency is not installed"
            raise ValueError(msg) from self._prophet_error

        assert self._prophet_class is not None  # for type-checkers
        working = df.copy()
        working = working.sort_index()
        working["ds"] = pd.to_datetime(working.index)
        if working["ds"].dt.tz is not None:
            working["ds"] = working["ds"].dt.tz_convert("UTC").dt.tz_localize(None)
        regressors: list[str] = []
        if exog_df is not None:
            exog_aligned = exog_df.copy()
            exog_aligned.index = working.index
            working = working.join(exog_aligned)
            regressors = list(exog_aligned.columns)

        model = self._prophet_class(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
        )
        for reg in regressors:
            model.add_regressor(reg)

        model.fit(working[["ds", "y", *regressors]])

        forecast_index = self._generate_future_index(pd.DatetimeIndex(df.index), horizon)
        future = pd.DataFrame({"ds": forecast_index})
        if future["ds"].dt.tz is not None:
            future["ds"] = future["ds"].dt.tz_convert("UTC").dt.tz_localize(None)

        if regressors:
            future_exog = (
                exog_future
                if exog_future is not None
                else self._default_future_exog(
                    exog_df if exog_df is not None else pd.DataFrame(index=df.index), forecast_index
                )
            )
            for reg in regressors:
                future[reg] = future_exog[reg].reset_index(drop=True)

        forecast_frame = model.predict(future)
        values = forecast_frame["yhat"].tolist()
        points = [(stamp.isoformat(), float(value)) for stamp, value in zip(forecast_index, values, strict=False)]
        diagnostics: dict[str, object] = {
            "observations": len(df),
            "model": "prophet",
            "components": [c for c in ("trend", "seasonality") if c in forecast_frame.columns],
        }
        if timezone and timezone != "UTC":
            diagnostics["source_timezone"] = timezone
        return ForecastResult(
            horizon=horizon,
            points=points,
            model_order=(0, 0, 0),
            diagnostics=diagnostics,
            timezone=timezone or "UTC",
            model="prophet",
        )

    def _ml_feature_row(
        self,
        ts: pd.Timestamp,
        history: list[float],
        position: int,
        lags: tuple[int, ...],
        exog_lookup: pd.DataFrame | None,
    ) -> dict[str, float]:
        features: dict[str, float] = {
            "time_index": float(position),
            "sin_week": math.sin(2 * math.pi * ts.dayofweek / 7.0),
            "cos_week": math.cos(2 * math.pi * ts.dayofweek / 7.0),
            "sin_year": math.sin(2 * math.pi * ts.dayofyear / 365.0),
            "cos_year": math.cos(2 * math.pi * ts.dayofyear / 365.0),
        }
        for lag in lags:
            idx = position - lag
            features[f"lag_{lag}"] = float(history[idx]) if idx >= 0 else float(history[0])

        if exog_lookup is not None and not exog_lookup.empty:
            row = exog_lookup.loc[ts] if ts in exog_lookup.index else exog_lookup.iloc[-1]
            for col in exog_lookup.columns:
                features[col] = float(cast(Any, row[col]))
        return features

    def _forecast_gradient_boosting(
        self,
        df: pd.DataFrame,
        horizon: int,
        timezone: str | None,
        *,
        exog_df: pd.DataFrame | None,
        exog_future: pd.DataFrame | None,
    ) -> ForecastResult:
        try:
            from sklearn.ensemble import GradientBoostingRegressor  # type: ignore[import-untyped]
        except Exception as exc:
            self._sklearn_error = exc
            raise ValueError("scikit-learn is required for gradient boosting forecasts") from exc

        lags: tuple[int, ...] = (1, 7, 14)
        history = [float(v) for v in df["y"].tolist()]
        feature_rows: list[dict[str, float]] = []
        targets: list[float] = []
        index_list = list(df.index)
        max_lag = max(lags)

        for position in range(max_lag, len(history)):
            ts = pd.Timestamp(index_list[position])
            feature_rows.append(self._ml_feature_row(ts, history, position, lags, exog_df))
            targets.append(history[position])

        if not feature_rows:
            return self._fallback(df, horizon, timezone, model="gradient_boosting")

        feature_frame = pd.DataFrame(feature_rows)
        model = GradientBoostingRegressor(random_state=42)
        model.fit(feature_frame, targets)
        feature_columns = list(feature_frame.columns)

        forecast_index = self._generate_future_index(pd.DatetimeIndex(df.index), horizon)
        exog_future_aligned = exog_future or (
            self._default_future_exog(exog_df, forecast_index) if exog_df is not None else None
        )
        predictions: list[tuple[str, float]] = []
        for _i, ts in enumerate(forecast_index):
            position = len(history)
            exog_lookup = None
            if exog_future_aligned is not None:
                exog_lookup = exog_future_aligned
            feature_row = self._ml_feature_row(pd.Timestamp(ts), history, position, lags, exog_lookup)
            row_df = pd.DataFrame([feature_row], columns=feature_columns).ffill().fillna(0.0)
            pred = float(model.predict(row_df)[0])
            history.append(pred)
            predictions.append((pd.Timestamp(ts).isoformat(), pred))

        diagnostics: dict[str, object] = {
            "observations": len(df),
            "model": "gradient_boosting",
            "lags": lags,
        }
        if timezone and timezone != "UTC":
            diagnostics["source_timezone"] = timezone

        return ForecastResult(
            horizon=horizon,
            points=predictions,
            model_order=(0, 0, 0),
            diagnostics=diagnostics,
            timezone=timezone or "UTC",
            model="gradient_boosting",
        )

    # ------------------------------------------------------------------
    # Evaluation utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _metric_mae(actual: Sequence[float], predicted: Sequence[float]) -> float:
        return float(np.mean(np.abs(np.subtract(actual, predicted))))

    @staticmethod
    def _metric_rmse(actual: Sequence[float], predicted: Sequence[float]) -> float:
        return float(np.sqrt(np.mean(np.square(np.subtract(actual, predicted)))))

    @staticmethod
    def _metric_mape(actual: Sequence[float], predicted: Sequence[float]) -> float | None:
        if not actual or any(a == 0 for a in actual):
            return None
        actual_arr = np.array(actual)
        predicted_arr = np.array(predicted)
        return float(np.mean(np.abs((actual_arr - predicted_arr) / actual_arr))) * 100

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
        """Perform rolling-origin backtesting across one or more models."""

        if horizon <= 0:
            raise ValueError("horizon must be positive")
        df, timezone = self._prepare_series(list(series))
        exog_df = self._prepare_exogenous(df, exogenous) if exogenous else None

        window = initial_window or max(self.minimum_observations, horizon * 2)
        stride = step or horizon
        model_keys = [self._normalise_model_key(model) for model in (models or ["arima"])]

        results: list[BacktestResult] = []
        for model_key in model_keys:
            registry_entry = self._model_registry.get(model_key)
            if registry_entry is None:
                results.append(
                    BacktestResult(
                        model=model_key,
                        folds=[],
                        metrics={},
                        tested_points=0,
                        available=False,
                        reason="Unknown model",
                        timezone=timezone or "UTC",
                    )
                )
                continue
            if not registry_entry.available:
                results.append(
                    BacktestResult(
                        model=model_key,
                        folds=[],
                        metrics={},
                        tested_points=0,
                        available=False,
                        reason="Model dependency unavailable",
                        timezone=timezone or "UTC",
                    )
                )
                continue

            folds: list[BacktestFold] = []
            position = window
            while position < len(df):
                test_horizon = min(horizon, len(df) - position)
                if test_horizon <= 0:
                    break
                train_slice = df.iloc[:position]
                test_slice = df.iloc[position : position + test_horizon]
                exog_train = exog_df.iloc[:position] if exog_df is not None else None
                exog_test = exog_df.iloc[position : position + test_horizon] if exog_df is not None else None

                forecast = self._dispatch_model(
                    model_key,
                    train_slice,
                    test_horizon,
                    timezone,
                    exog_df=exog_train,
                    exog_future=exog_test,
                )
                actual_values = [float(v) for v in test_slice["y"].tolist()]
                predicted_values = [point[1] for point in forecast.points]
                mae = self._metric_mae(actual_values, predicted_values)
                rmse = self._metric_rmse(actual_values, predicted_values)
                mape = self._metric_mape(actual_values, predicted_values)
                folds.append(
                    BacktestFold(
                        start=pd.Timestamp(train_slice.index[0]).isoformat(),
                        end=pd.Timestamp(test_slice.index[-1]).isoformat(),
                        horizon=test_horizon,
                        actual=list(zip((ts.isoformat() for ts in test_slice.index), actual_values, strict=False)),
                        forecast=forecast.points,
                        mae=mae,
                        rmse=rmse,
                        mape=mape,
                    )
                )
                position += stride

            if not folds:
                results.append(
                    BacktestResult(
                        model=model_key,
                        folds=[],
                        metrics={},
                        tested_points=0,
                        available=False,
                        reason="Insufficient data for backtesting",
                        timezone=timezone or "UTC",
                    )
                )
                continue

            metrics = {
                "mae": float(np.mean([fold.mae for fold in folds])),
                "rmse": float(np.mean([fold.rmse for fold in folds])),
                "mape": (
                    float(np.mean([fold.mape for fold in folds if fold.mape is not None]))
                    if any(fold.mape is not None for fold in folds)
                    else None
                ),
            }
            tested_points = sum(len(fold.actual) for fold in folds)
            results.append(
                BacktestResult(
                    model=model_key,
                    folds=folds,
                    metrics=metrics,
                    tested_points=tested_points,
                    available=True,
                    timezone=timezone or "UTC",
                )
            )

        return results

    def causal_impact(
        self,
        series: Sequence[tuple[str | date, float]],
        event_start: str | date | datetime,
        *,
        event_end: str | date | datetime | None = None,
        interventions: Mapping[str, Sequence[tuple[str | date, float]]] | None = None,
        model: str = "arima",
    ) -> CausalImpactResult:
        """Estimate the impact of an event window using a counterfactual forecast."""

        df, timezone = self._prepare_series(list(series))
        if df.empty:
            raise ValueError("Series must contain observations")

        start_ts = pd.to_datetime(event_start)
        end_ts = pd.to_datetime(event_end) if event_end is not None else df.index[-1]
        if start_ts not in df.index:
            df = df.sort_index()
        pre_event = df.loc[df.index < start_ts]
        post_event = df.loc[(df.index >= start_ts) & (df.index <= end_ts)]
        if len(pre_event) < self.minimum_observations:
            raise ValueError("Not enough pre-event observations for causal impact analysis")
        if post_event.empty:
            raise ValueError("Event window contains no observations")

        exog_df = self._prepare_exogenous(df, interventions) if interventions else None
        exog_pre = exog_df.loc[pre_event.index] if exog_df is not None else None
        exog_post = exog_df.loc[post_event.index] if exog_df is not None else None

        forecast = self._dispatch_model(
            self._normalise_model_key(model),
            pre_event,
            len(post_event),
            timezone,
            exog_df=exog_pre,
            exog_future=exog_post,
        )

        predicted = [point[1] for point in forecast.points]
        actual = [float(v) for v in post_event["y"].tolist()]
        impacts = [a - p for a, p in zip(actual, predicted, strict=False)]
        avg_impact = float(np.mean(impacts))
        cumulative = float(np.sum(impacts))

        # Approximate a simple two-sided z-test using the pre-event variance.
        std_dev = float(np.std(pre_event["y"])) if len(pre_event) > 1 else 0.0
        p_value = None
        if std_dev > 0:
            z = abs(avg_impact) / (std_dev / sqrt(len(post_event)))
            p_value = float(math.erfc(z / math.sqrt(2)))

        points = [
            ImpactPoint(timestamp=ts.isoformat(), actual=a, predicted=p, impact=i)
            for ts, a, p, i in zip(post_event.index, actual, predicted, impacts, strict=False)
        ]
        diagnostics: dict[str, object] = {
            "model": forecast.model,
            "pre_event_observations": len(pre_event),
            "post_event_observations": len(post_event),
        }
        if timezone and timezone != "UTC":
            diagnostics["source_timezone"] = timezone

        return CausalImpactResult(
            model=forecast.model,
            event_start=start_ts.isoformat(),
            event_end=end_ts.isoformat(),
            average_impact=avg_impact,
            cumulative_impact=cumulative,
            p_value=p_value,
            points=points,
            diagnostics=diagnostics,
            timezone=timezone or "UTC",
        )
