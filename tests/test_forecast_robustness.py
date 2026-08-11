"""Forecast boundary tests for finite values, cadence, timezones, and output safety."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from apps.api.services.forecast_service import ForecastResult, ForecastService


def _daily_series(count: int = 8, *, start: str = "2024-01-01") -> list[tuple[pd.Timestamp, float]]:
    return [
        (timestamp, float(index + 1)) for index, timestamp in enumerate(pd.date_range(start, periods=count, freq="D"))
    ]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_target_series_rejects_non_finite_values(value: float) -> None:
    service = ForecastService(minimum_observations=10)

    with pytest.raises(ValueError, match="Series values must be finite"):
        service.forecast_series([("2024-01-01", value)], horizon=1)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_regressors_reject_non_finite_values(value: float) -> None:
    service = ForecastService(minimum_observations=10)
    series = _daily_series()
    regressors = {"driver": [(timestamp, value if index == 2 else 1.0) for index, (timestamp, _) in enumerate(series)]}

    with pytest.raises(ValueError, match="Regressor 'driver' values must be finite"):
        service.forecast_series(series, horizon=2, exogenous=regressors)


def test_regressor_alignment_requires_first_target_timestamp() -> None:
    service = ForecastService(minimum_observations=10)
    series = _daily_series()
    regressors = {"driver": [(timestamp, 1.0) for timestamp, _ in series[1:]]}

    with pytest.raises(ValueError, match="must begin at the first target timestamp"):
        service.forecast_series(series, horizon=2, exogenous=regressors)


def test_regressor_rejects_timestamp_outside_target() -> None:
    service = ForecastService(minimum_observations=10)
    series = _daily_series()
    regressors = {
        "driver": [
            *(timestamp_value for timestamp_value in ((timestamp, 1.0) for timestamp, _ in series)),
            (pd.Timestamp("2024-02-01"), 1.0),
        ]
    }

    with pytest.raises(ValueError, match="timestamps must align with the target series"):
        service.forecast_series(series, horizon=2, exogenous=regressors)


def test_regressor_rejects_empty_and_trimmed_duplicate_names() -> None:
    service = ForecastService(minimum_observations=10)
    series = _daily_series()
    values = [(timestamp, 1.0) for timestamp, _ in series]

    with pytest.raises(ValueError, match="Regressor names must not be empty"):
        service.forecast_series(series, horizon=2, exogenous={"  ": values})

    with pytest.raises(ValueError, match="Regressor names must be unique"):
        service.forecast_series(series, horizon=2, exogenous={"driver": values, " driver ": values})


def test_duplicate_timestamps_keep_last_supplied_value_and_report_resolution() -> None:
    service = ForecastService(minimum_observations=10)
    series = [
        ("2024-01-01", 1.0),
        ("2024-01-02", 2.0),
        ("2024-01-02", 9.0),
        ("2024-01-03", 3.0),
    ]

    result = service.forecast_series(series, horizon=2)

    assert result.points == [("2024-01-04T00:00:00", 3.0), ("2024-01-05T00:00:00", 3.0)]
    assert result.diagnostics is not None
    assert result.diagnostics["duplicate_timestamps_resolved"] == 1
    assert result.diagnostics["cadence"] == "daily"


def test_irregular_multi_point_cadence_is_rejected() -> None:
    service = ForecastService(minimum_observations=10)

    with pytest.raises(ValueError, match="must use a regular cadence"):
        service.forecast_series(
            [("2024-01-01", 1.0), ("2024-01-02", 2.0), ("2024-01-04", 3.0)],
            horizon=1,
        )


def test_one_and_two_point_cadence_policies_are_explicit() -> None:
    service = ForecastService(minimum_observations=10)

    single = service.forecast_series([("2024-01-01", -2.0)], horizon=2)
    assert single.diagnostics is not None
    assert single.diagnostics["cadence"] == "single-observation-daily-default"
    assert [point[0] for point in single.points] == ["2024-01-02T00:00:00", "2024-01-03T00:00:00"]

    two_point = service.forecast_series(
        [("2024-01-01", 0.0), ("2024-01-03", 4.0)],
        horizon=2,
    )
    assert two_point.diagnostics is not None
    assert str(two_point.diagnostics["cadence"]).startswith("two-point-observed-interval:")
    assert [point[0] for point in two_point.points] == ["2024-01-05T00:00:00", "2024-01-07T00:00:00"]


def test_mixed_naive_and_aware_timestamps_are_rejected() -> None:
    service = ForecastService(minimum_observations=10)

    with pytest.raises(ValueError, match="cannot mix naive and timezone-aware"):
        service.forecast_series(
            [
                (datetime(2024, 1, 1), 1.0),
                (datetime(2024, 1, 2, tzinfo=ZoneInfo("UTC")), 2.0),
            ],
            horizon=1,
        )


def test_regressor_timezone_must_match_target_timezone() -> None:
    service = ForecastService(minimum_observations=10)
    target = [(datetime(2024, 1, 1 + index, tzinfo=ZoneInfo("America/New_York")), float(index)) for index in range(4)]
    regressors = {
        "driver": [(datetime(2024, 1, 1 + index, tzinfo=ZoneInfo("UTC")), float(index)) for index in range(4)]
    }

    with pytest.raises(ValueError, match="must use the target series timezone"):
        service.forecast_series(target, horizon=1, exogenous=regressors)


@pytest.mark.parametrize(
    ("start", "expected_hour", "expected_offset"),
    [
        ("2024-03-08 12:00", 12, "-04:00"),
        ("2024-11-01 12:00", 12, "-05:00"),
    ],
)
def test_daily_cadence_preserves_local_time_across_dst(
    start: str,
    expected_hour: int,
    expected_offset: str,
) -> None:
    service = ForecastService(minimum_observations=10)
    index = pd.date_range(start, periods=4, freq="D", tz="America/New_York")
    series = [(timestamp, float(position)) for position, timestamp in enumerate(index)]

    result = service.forecast_series(series, horizon=2)

    future = [pd.Timestamp(timestamp) for timestamp, _ in result.points]
    assert all(timestamp.hour == expected_hour for timestamp in future)
    assert result.points[-1][0].endswith(expected_offset)
    assert result.diagnostics is not None
    assert result.diagnostics["cadence"] == "daily"


@pytest.mark.parametrize(
    "start",
    ["2024-03-10 00:00", "2024-11-03 00:00"],
)
def test_hourly_cadence_remains_ordered_across_dst(start: str) -> None:
    service = ForecastService(minimum_observations=10)
    index = pd.date_range(start, periods=5, freq="h", tz="America/New_York")
    series = [(timestamp, float(position)) for position, timestamp in enumerate(index)]

    result = service.forecast_series(series, horizon=3)

    future = [pd.Timestamp(timestamp) for timestamp, _ in result.points]
    assert future == sorted(future)
    assert len({timestamp.isoformat() for timestamp in future}) == 3
    assert result.diagnostics is not None
    assert result.diagnostics["cadence"] == "hourly"


def test_non_finite_forecast_output_is_rejected() -> None:
    class NonFiniteService(ForecastService):
        def _dispatch_model(self, *args, **kwargs) -> ForecastResult:  # type: ignore[no-untyped-def]
            return ForecastResult(
                horizon=1,
                points=[("2024-01-09T00:00:00", float("nan"))],
                model_order=(0, 0, 0),
                diagnostics={"metric": 1.0},
                timezone="UTC",
                model="arima",
            )

    with pytest.raises(ValueError, match="Forecast output values must be finite"):
        NonFiniteService().forecast_series(_daily_series(), horizon=1)


def test_non_finite_diagnostics_are_rejected() -> None:
    class NonFiniteService(ForecastService):
        def _dispatch_model(self, *args, **kwargs) -> ForecastResult:  # type: ignore[no-untyped-def]
            return ForecastResult(
                horizon=1,
                points=[("2024-01-09T00:00:00", 1.0)],
                model_order=(0, 0, 0),
                diagnostics={"metric": float("inf")},
                timezone="UTC",
                model="arima",
            )

    with pytest.raises(ValueError, match="Forecast diagnostics must be finite"):
        NonFiniteService().forecast_series(_daily_series(), horizon=1)


def test_metrics_reject_non_finite_values_and_mape_handles_zero_denominator() -> None:
    with pytest.raises(ValueError, match="Predicted values must be finite"):
        ForecastService._metric_mae([1.0], [float("inf")])

    assert ForecastService._metric_mape([0.0, 2.0], [1.0, 2.0]) is None
    assert ForecastService._metric_rmse([-1.0, 1.0], [-1.0, 1.0]) == pytest.approx(0.0)


def test_backtest_validates_window_and_step_at_service_boundary() -> None:
    service = ForecastService()

    with pytest.raises(ValueError, match="initial_window must be positive"):
        service.backtest(_daily_series(), initial_window=0)
    with pytest.raises(ValueError, match="step must be positive"):
        service.backtest(_daily_series(), step=0)


def test_causal_event_window_rejects_naive_date_for_aware_utc_series() -> None:
    service = ForecastService(minimum_observations=3)
    index = pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC")
    series = [(timestamp, float(position)) for position, timestamp in enumerate(index)]

    with pytest.raises(ValueError, match="event_start must use the target series timezone"):
        service.causal_impact(series, event_start="2024-01-08")


def test_causal_event_window_must_be_ordered_and_contained() -> None:
    service = ForecastService(minimum_observations=3)
    series = _daily_series(count=10)

    with pytest.raises(ValueError, match="event_end must not precede event_start"):
        service.causal_impact(series, event_start="2024-01-08", event_end="2024-01-07")
    with pytest.raises(ValueError, match="must be contained within the target series"):
        service.causal_impact(series, event_start="2024-01-08", event_end="2024-02-01")


def test_negative_constant_and_zero_heavy_series_remain_valid() -> None:
    service = ForecastService(minimum_observations=10)
    base = datetime(2024, 1, 1)
    series = [(base + timedelta(days=index), value) for index, value in enumerate([-5.0, 0.0, 0.0, -5.0])]

    result = service.forecast_series(series, horizon=2)

    assert all(math_value == pytest.approx(-5.0) for _, math_value in result.points)
