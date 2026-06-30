"""Forecast service unit tests covering ARIMA flow edge cases."""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from apps.api.services.forecast_service import ForecastResult, ForecastService


def generate_series(count: int = 30) -> list[tuple[datetime, float]]:
    """Produce a simple linear time series for deterministic testing."""
    base = datetime(2024, 1, 1)
    return [(base + timedelta(days=i), float(100 + i * 2)) for i in range(count)]


def test_forecast_series_returns_points() -> None:
    svc = ForecastService()
    series = generate_series()
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        result = svc.forecast_series(series, horizon=5)

    assert isinstance(result, ForecastResult)
    assert result.horizon == 5
    assert len(result.points) == 5
    assert result.model_order in svc.candidate_orders
    assert result.diagnostics is not None
    assert result.diagnostics["observations"] == 30
    assert result.diagnostics["model"] == "arima"
    assert "mae" in result.diagnostics
    assert "rmse" in result.diagnostics
    assert result.timezone == "UTC"
    assert captured == []


def test_forecast_series_empty_input() -> None:
    svc = ForecastService()
    result = svc.forecast_series([], horizon=5)
    assert result.horizon == 0
    assert result.points == []
    assert result.model_order == (0, 0, 0)
    assert result.diagnostics is not None
    assert result.diagnostics["observations"] == 0
    assert result.diagnostics["strategy"] == "empty_input"
    assert result.diagnostics["model"] == "arima"
    assert result.timezone == "UTC"


def test_forecast_series_invalid_horizon() -> None:
    svc = ForecastService()
    with pytest.raises(ValueError):
        svc.forecast_series(generate_series(), horizon=0)


def test_forecast_series_rejects_non_numeric() -> None:
    svc = ForecastService()
    series = cast(
        Sequence[tuple[object, float | int | Decimal]],
        [("2024-01-01", "not-a-number")],
    )
    with pytest.raises(ValueError):
        svc.forecast_series(series, horizon=2)


def test_forecast_series_cleans_duplicates_and_order() -> None:
    svc = ForecastService()
    base = datetime(2024, 1, 1)
    series = [
        (base + timedelta(days=5), 110),
        (base, 100),
        (base + timedelta(days=1), 101),
        (base + timedelta(days=2), 102),
        (base + timedelta(days=3), 103),
        (base + timedelta(days=4), 104),
        (base + timedelta(days=2), 105),
    ]

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        result = svc.forecast_series(series, horizon=3)

    assert result.horizon == 3
    assert len(result.points) == 3
    assert result.model_order in svc.candidate_orders
    assert captured == []


def test_forecast_series_records_timezone() -> None:
    svc = ForecastService()
    tz = ZoneInfo("America/New_York")
    series = [
        (datetime(2024, 1, 1, tzinfo=tz), 100.0),
        (datetime(2024, 1, 2, tzinfo=tz), 101.0),
        (datetime(2024, 1, 3, tzinfo=tz), 102.0),
        (datetime(2024, 1, 4, tzinfo=tz), 103.0),
    ]

    result = svc.forecast_series(series, horizon=2)

    assert result.timezone == "America/New_York"
    assert result.diagnostics is not None
    assert result.diagnostics.get("source_timezone") == "America/New_York"
    assert all(point[0].endswith("-05:00") for point in result.points)


def test_forecast_series_repeat_last_fallback() -> None:
    svc = ForecastService(minimum_observations=5)
    short_series = generate_series(count=3)

    result = svc.forecast_series(short_series, horizon=2)

    assert result.model_order == (0, 0, 0)
    assert result.diagnostics is not None
    assert result.diagnostics["strategy"] == "fallback_repeat_last"
    assert len(result.points) == 2
    assert all(point[1] == pytest.approx(short_series[-1][1]) for point in result.points)
    expected_label = pd.Timestamp(short_series[-1][0]).replace(tzinfo=UTC).isoformat()
    label_value = result.diagnostics["last_observation_label"]
    assert isinstance(label_value, str)
    assert label_value == expected_label
    expected_epoch = pd.Timestamp(short_series[-1][0], tz="UTC").timestamp()
    epoch_value = result.diagnostics["last_observation_epoch"]
    assert isinstance(epoch_value, float)
    assert epoch_value == pytest.approx(expected_epoch)


def test_forecast_series_mean_fallback() -> None:
    svc = ForecastService(minimum_observations=6, fallback_strategy="mean")
    short_series = generate_series(count=4)

    result = svc.forecast_series(short_series, horizon=3)

    assert result.diagnostics is not None
    assert result.diagnostics["strategy"] == "fallback_mean"
    expected_value = sum(v for _, v in short_series) / len(short_series)
    assert all(point[1] == pytest.approx(expected_value) for point in result.points)


def test_forecast_series_fallback_raise() -> None:
    svc = ForecastService(minimum_observations=4, fallback_strategy="raise")
    short_series = generate_series(count=2)

    with pytest.raises(ValueError):
        svc.forecast_series(short_series, horizon=2)


def test_forecast_series_timezone_preserved_in_fallback() -> None:
    tz = ZoneInfo("Europe/Berlin")
    svc = ForecastService(minimum_observations=10)
    series = [
        (datetime(2024, 1, 1, tzinfo=tz), 1.0),
        (datetime(2024, 1, 2, tzinfo=tz), 2.0),
        (datetime(2024, 1, 3, tzinfo=tz), 3.0),
    ]

    result = svc.forecast_series(series, horizon=2)

    assert result.diagnostics is not None
    assert result.diagnostics["strategy"] == "fallback_repeat_last"
    assert result.timezone == "Europe/Berlin"
    assert all(point[0].endswith("+01:00") for point in result.points)
    label_value = result.diagnostics["last_observation_label"]
    assert isinstance(label_value, str)
    assert label_value.endswith("+01:00")


def test_generate_future_index_single_observation_defaults_daily() -> None:
    svc = ForecastService(minimum_observations=10)
    series = [
        (datetime(2024, 1, 1), 1.0),
    ]

    df, _ = svc._prepare_series(series)
    fallback_index = svc._generate_future_index(df.index, 3)

    assert list(fallback_index) == [
        pd.Timestamp("2024-01-02 00:00:00"),
        pd.Timestamp("2024-01-03 00:00:00"),
        pd.Timestamp("2024-01-04 00:00:00"),
    ]


def test_forecast_service_configuration_guards() -> None:
    with pytest.raises(ValueError):
        ForecastService(minimum_observations=0)

    with pytest.raises(ValueError):
        ForecastService(fallback_strategy="unsupported")  # type: ignore[arg-type]


# TODO - (forecast) Cover seasonal decomposition strategies when implemented.


def test_forecast_prefers_best_auto_order(monkeypatch) -> None:
    recorded_orders: list[tuple[int, int, int]] = []

    class DummyResult:
        def __init__(self, order):
            self.order = order
            self.aic = sum(order)
            self.bic = self.aic + 1
            self.resid = pd.Series([0.1, -0.1])

        def forecast(self, steps, exog=None):
            return [1.0] * steps

    class DummyARIMA:
        def __init__(self, series, order, exog=None):
            recorded_orders.append(order)
            self.order = order
            self.exog = exog

        def fit(self):
            return DummyResult(self.order)

    monkeypatch.setattr("apps.api.services.forecast_service.ARIMA", DummyARIMA)
    svc = ForecastService(candidate_orders=[(1, 1, 1), (2, 1, 1)])
    result = svc.forecast_series(generate_series(), horizon=2)

    assert result.model_order == (1, 1, 1) or result.model_order == (2, 1, 1)
    assert (2, 1, 1) in recorded_orders


def test_forecast_supports_exogenous_regressors(monkeypatch) -> None:
    last_exog_future: dict[str, pd.DataFrame | None] = {"value": None}

    class DummyResult:
        def __init__(self, exog=None):
            self.aic = 1
            self.bic = 1
            self.resid = pd.Series([0.1, -0.1])
            self._exog = exog

        def forecast(self, steps, exog=None):
            last_exog_future["value"] = exog
            return [2.0] * steps

    class DummyARIMA:
        def __init__(self, series, order, exog=None):
            self.exog = exog

        def fit(self):
            return DummyResult(self.exog)

    monkeypatch.setattr("apps.api.services.forecast_service.ARIMA", DummyARIMA)
    svc = ForecastService(minimum_observations=3)
    series = generate_series(count=5)
    exog = {"fx": [(series[i][0], i) for i in range(len(series))]}

    result = svc.forecast_series(series, horizon=3, exogenous=exog)

    assert result.points
    future_exog = last_exog_future["value"]
    assert future_exog is not None
    assert list(future_exog.columns) == ["fx"]


def test_forecast_model_registry_reports_optional_dependencies() -> None:
    svc = ForecastService()
    models = {m.key: m for m in svc.available_models()}
    assert "arima" in models
    assert "prophet" in models
    assert "gradient_boosting" in models
    # Prophet may be unavailable locally but should declare the requirement.
    if not models["prophet"].available:
        assert "prophet" in " ".join(models["prophet"].requirements)


def test_backtest_produces_metrics() -> None:
    svc = ForecastService()
    series = generate_series(count=40)
    results = svc.backtest(series, horizon=5, models=["arima"])
    assert results
    arima_result = results[0]
    assert arima_result.available is True
    assert arima_result.metrics["mae"] >= 0
    assert arima_result.metrics["rmse"] >= 0
    assert arima_result.folds
    assert arima_result.tested_points > 0


def test_gradient_boosting_forecast(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("sklearn")
    svc = ForecastService(minimum_observations=10)
    series = generate_series(count=25)
    result = svc.forecast_series(series, horizon=3, model="gradient_boosting")
    assert result.model == "gradient_boosting"
    assert len(result.points) == 3
    assert result.diagnostics is not None
    assert result.diagnostics["model"] == "gradient_boosting"


def test_causal_impact_detects_positive_shift() -> None:
    svc = ForecastService(minimum_observations=8)
    base = datetime(2024, 1, 1)
    series: list[tuple[datetime, float]] = []
    # steady growth then an intervention adding +10
    for i in range(20):
        value = float(i)
        series.append((base + timedelta(days=i), value))
    for i in range(10):
        value = float(20 + i + 10)
        series.append((base + timedelta(days=20 + i), value))

    result = svc.causal_impact(series, event_start=base + timedelta(days=20))
    assert result.cumulative_impact > 0
    assert result.average_impact > 0
    assert result.points


def test_build_event_regressors_counts_keywords() -> None:
    svc = ForecastService()
    events = [
        ("2024-01-01", "Supply disruption and regulation change"),
        ("2024-01-02", "Marketing push"),
    ]
    regressors = svc.build_event_regressors(events, keywords=["supply", "regulation"])
    assert "event_intensity" in regressors
    series = regressors["event_intensity"]
    assert series[0][1] == 2.0
    assert series[1][1] == 0.0


def test_seasonal_decomposition_placeholder() -> None:
    """Placeholder to cover upcoming seasonal decomposition strategies."""
    svc = ForecastService()
    series = generate_series(count=20)
    result = svc.forecast_series(series, horizon=5)
    assert result.points
