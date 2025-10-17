from __future__ import annotations

from datetime import datetime, timedelta
import warnings

import pytest

from apps.api.services.forecast_service import ForecastResult, ForecastService


def generate_series(count: int = 30):
    base = datetime(2024, 1, 1)
    return [(base + timedelta(days=i), 100 + i * 2) for i in range(count)]


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
    assert captured == []


def test_forecast_series_empty_input() -> None:
    svc = ForecastService()
    result = svc.forecast_series([], horizon=5)
    assert result.horizon == 0
    assert result.points == []
    assert result.model_order == (0, 0, 0)


def test_forecast_series_invalid_horizon() -> None:
    svc = ForecastService()
    with pytest.raises(ValueError):
        svc.forecast_series(generate_series(), horizon=0)


def test_forecast_series_rejects_non_numeric() -> None:
    svc = ForecastService()
    series = [("2024-01-01", "not-a-number")]
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
