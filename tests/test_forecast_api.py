"""Forecast router tests for tenant-first execution and sanitized API contracts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from apps.api.routers import forecast as forecast_router
from apps.api.schemas import BacktestRequest, CausalImpactRequest, ForecastRequest
from apps.api.services.forecast_service import (
    BacktestFold,
    BacktestResult,
    CausalImpactResult,
    ForecastResult,
    ImpactPoint,
    ModelInfo,
)
from fastapi import HTTPException


class _SuccessfulService:
    def forecast_series(self, series, horizon, *, exogenous, model):  # type: ignore[no-untyped-def]
        assert len(series) == 3
        assert horizon == 2
        assert exogenous == {"driver": [("2024-01-01", 1.0)]}
        assert model == "arima"
        return ForecastResult(
            horizon=2,
            points=[("2024-01-04T00:00:00", 4.0), ("2024-01-05T00:00:00", 5.0)],
            model_order=(1, 1, 0),
            diagnostics={"cadence": "daily"},
            timezone="UTC",
            model="arima",
        )

    def available_models(self):  # type: ignore[no-untyped-def]
        return [
            ModelInfo(
                key="arima",
                name="Auto ARIMA",
                family="statistical",
                description="Deterministic test model",
                supports_exogenous=True,
                available=True,
            )
        ]

    def backtest(self, series, *, horizon, models, exogenous, initial_window, step):  # type: ignore[no-untyped-def]
        assert len(series) == 6
        assert horizon == 2
        assert models == ["arima"]
        assert exogenous is None
        assert initial_window == 4
        assert step == 2
        return [
            BacktestResult(
                model="arima",
                folds=[
                    BacktestFold(
                        start="2024-01-01T00:00:00",
                        end="2024-01-06T00:00:00",
                        horizon=2,
                        actual=[("2024-01-05T00:00:00", 5.0), ("2024-01-06T00:00:00", 6.0)],
                        forecast=[("2024-01-05T00:00:00", 4.5), ("2024-01-06T00:00:00", 5.5)],
                        mae=0.5,
                        rmse=0.5,
                        mape=9.1666666667,
                    )
                ],
                metrics={"mae": 0.5, "rmse": 0.5, "mape": 9.1666666667},
                tested_points=2,
                available=True,
                timezone="UTC",
            )
        ]

    def causal_impact(self, series, *, event_start, event_end, interventions, model):  # type: ignore[no-untyped-def]
        assert len(series) == 6
        assert str(event_start) == "2024-01-05"
        assert str(event_end) == "2024-01-06"
        assert interventions is None
        assert model == "arima"
        return CausalImpactResult(
            model="arima",
            event_start="2024-01-05T00:00:00",
            event_end="2024-01-06T00:00:00",
            average_impact=1.5,
            cumulative_impact=3.0,
            p_value=0.25,
            points=[
                ImpactPoint(
                    timestamp="2024-01-05T00:00:00",
                    actual=5.0,
                    predicted=3.5,
                    impact=1.5,
                )
            ],
            diagnostics={"cadence": "daily"},
            timezone="UTC",
        )


def _authorize(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    def authorize(**kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["organization_id"] == 7
        events.append("authorize")
        return SimpleNamespace(organization=SimpleNamespace(id=7))

    monkeypatch.setattr(forecast_router, "get_current_organization", authorize)


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=11)


def _series(count: int = 6) -> list[tuple[str, float]]:
    return [(f"2024-01-{index + 1:02d}", float(index + 1)) for index in range(count)]


def test_forecast_routes_return_typed_success_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    _authorize(monkeypatch, events)
    monkeypatch.setattr(forecast_router, "_FORECAST_SERVICE", _SuccessfulService())

    forecast_response = forecast_router.forecast_series(
        ForecastRequest(
            organization_id=7,
            series=_series(3),
            horizon=2,
            model="arima",
            regressors={"driver": [("2024-01-01", 1.0)]},
        ),
        s=object(),  # type: ignore[arg-type]
        current_user=_user(),  # type: ignore[arg-type]
    )
    model_response = forecast_router.list_models(
        organization_id=7,
        s=object(),  # type: ignore[arg-type]
        current_user=_user(),  # type: ignore[arg-type]
    )
    backtest_response = forecast_router.backtest_series(
        BacktestRequest(
            organization_id=7,
            series=_series(),
            horizon=2,
            models=["arima"],
            initial_window=4,
            step=2,
        ),
        s=object(),  # type: ignore[arg-type]
        current_user=_user(),  # type: ignore[arg-type]
    )
    impact_response = forecast_router.causal_impact(
        CausalImpactRequest(
            organization_id=7,
            series=_series(),
            event_start="2024-01-05",
            event_end="2024-01-06",
            model="arima",
        ),
        s=object(),  # type: ignore[arg-type]
        current_user=_user(),  # type: ignore[arg-type]
    )

    assert forecast_response.forecast[-1] == ("2024-01-05T00:00:00", 5.0)
    assert forecast_response.diagnostics == {"cadence": "daily"}
    assert model_response[0].key == "arima"
    assert backtest_response[0].folds[0].mae == pytest.approx(0.5)
    assert impact_response.points[0].impact == pytest.approx(1.5)
    assert events == ["authorize", "authorize", "authorize", "authorize"]


@pytest.mark.parametrize("route_name", ["series", "models", "backtest", "impact"])
def test_tenant_authorization_runs_before_forecast_work(
    monkeypatch: pytest.MonkeyPatch,
    route_name: str,
) -> None:
    def deny(**_kwargs):  # type: ignore[no-untyped-def]
        raise HTTPException(status_code=403, detail="denied")

    class ShouldNotRun:
        def __getattr__(self, name: str):
            raise AssertionError(f"forecast service must not run before authorization: {name}")

    monkeypatch.setattr(forecast_router, "get_current_organization", deny)
    monkeypatch.setattr(forecast_router, "_FORECAST_SERVICE", ShouldNotRun())

    with pytest.raises(HTTPException) as exc_info:
        if route_name == "series":
            forecast_router.forecast_series(
                ForecastRequest(organization_id=7, series=_series(3), horizon=2),
                s=object(),  # type: ignore[arg-type]
                current_user=_user(),  # type: ignore[arg-type]
            )
        elif route_name == "models":
            forecast_router.list_models(
                organization_id=7,
                s=object(),  # type: ignore[arg-type]
                current_user=_user(),  # type: ignore[arg-type]
            )
        elif route_name == "backtest":
            forecast_router.backtest_series(
                BacktestRequest(organization_id=7, series=_series(), horizon=2),
                s=object(),  # type: ignore[arg-type]
                current_user=_user(),  # type: ignore[arg-type]
            )
        else:
            forecast_router.causal_impact(
                CausalImpactRequest(
                    organization_id=7,
                    series=_series(),
                    event_start="2024-01-05",
                ),
                s=object(),  # type: ignore[arg-type]
                current_user=_user(),  # type: ignore[arg-type]
            )

    assert exc_info.value.status_code == 403


def test_forecast_series_rejects_short_input_before_model_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    _authorize(monkeypatch, events)
    monkeypatch.setattr(forecast_router, "_FORECAST_SERVICE", _SuccessfulService())

    with pytest.raises(HTTPException) as exc_info:
        forecast_router.forecast_series(
            ForecastRequest(organization_id=7, series=_series(2), horizon=3),
            s=object(),  # type: ignore[arg-type]
            current_user=_user(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Series length must be at least the requested horizon"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Series values must be finite", "Series values must be finite"),
        ("internal-library-detail", "Forecast request could not be evaluated"),
        ("", "Forecast request could not be evaluated"),
    ],
)
def test_value_errors_use_allowlisted_sanitized_details(
    monkeypatch: pytest.MonkeyPatch,
    message: str,
    expected: str,
) -> None:
    class FailingService:
        def forecast_series(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise ValueError(message)

    events: list[str] = []
    _authorize(monkeypatch, events)
    monkeypatch.setattr(forecast_router, "_FORECAST_SERVICE", FailingService())

    with pytest.raises(HTTPException) as exc_info:
        forecast_router.forecast_series(
            ForecastRequest(organization_id=7, series=_series(3), horizon=2),
            s=object(),  # type: ignore[arg-type]
            current_user=_user(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == expected
    assert "internal-library-detail" not in str(exc_info.value.detail)


def test_unexpected_forecast_failures_are_generic_and_logs_exclude_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "DO-NOT-EXPOSE"

    class FailingService:
        def available_models(self):  # type: ignore[no-untyped-def]
            raise RuntimeError(marker)

    events: list[str] = []
    _authorize(monkeypatch, events)
    monkeypatch.setattr(forecast_router, "_FORECAST_SERVICE", FailingService())

    with caplog.at_level("WARNING"), pytest.raises(HTTPException) as exc_info:
        forecast_router.list_models(
            organization_id=7,
            s=object(),  # type: ignore[arg-type]
            current_user=_user(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Forecast operation could not be completed"
    assert marker not in caplog.text
    assert any(getattr(record, "operation", None) == "models" for record in caplog.records)
    assert any(getattr(record, "error_type", None) == "RuntimeError" for record in caplog.records)


def test_validation_detail_rejects_oversized_messages() -> None:
    detail = forecast_router._safe_validation_detail(ValueError("Series " + "x" * 300))
    assert detail == "Forecast request could not be evaluated"
