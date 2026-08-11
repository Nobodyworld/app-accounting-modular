# Forecasting

Modular Accounting provides authenticated, tenant-scoped forecasting, rolling backtests, causal-impact analysis, and model discovery. The forecast surface remains an Early Beta analytical control. It is not a financial prediction guarantee, automated accounting conclusion, or substitute for model governance.

## Supported models

The model engine currently exposes:

- **ARIMA** — baseline statistical model with bounded candidate-order selection.
- **Gradient boosting** — scikit-learn regressor using lag and calendar features.
- **Prophet** — optional model reported as unavailable when its dependency is not installed.

All models use the same validated `ForecastService` boundary. The original model implementations remain isolated behind that boundary so input, cadence, output, metric, diagnostic, and error contracts apply consistently.

## Input contract

### Finite numeric values

Target observations, regressors, interventions, model predictions, backtest values, metrics, causal-impact values, p-values, and numeric diagnostics must be finite. The service rejects:

- `NaN`;
- positive or negative infinity;
- non-numeric values; and
- values that cannot be represented as finite floats.

Legitimate negative and zero observations remain valid. Invalid exogenous values are not converted to zero.

### Timestamp and duplicate policy

Timestamps are sorted before modeling. Exact duplicate timestamps use a deterministic **last supplied value wins** rule. The result diagnostics include `duplicate_timestamps_resolved`.

A series must not mix naive and timezone-aware timestamps, and all aware timestamps must use one compatible timezone. Regressors and interventions must use the target series timezone.

### Cadence policy

The future index is derived under an explicit policy:

| Observations | Policy |
| --- | --- |
| One timestamp | Daily fallback cadence, reported as `single-observation-daily-default` |
| Two timestamps | Positive observed interval, reported with `two-point-observed-interval:` |
| Three or more timestamps | A regular pandas-compatible frequency must be inferable; irregular cadence is rejected |

The service no longer extrapolates an irregular multi-point series from only its final interval. Daily and hourly timezone-aware frequencies preserve local-time cadence across daylight-saving transitions.

### Regressor and intervention alignment

Regressor names must be nonempty and unique after trimming. Regressor timestamps must be drawn from the target timeline. Forward-fill is allowed only after a regressor supplies a value at the first target timestamp; leading gaps and out-of-range timestamps are rejected. Future exogenous values use the last validated finite row.

### Bounds

Request schemas retain the centralized application limits:

- maximum target-series length: 10,000 observations;
- maximum forecast horizon: 365;
- maximum regressors: 32;
- maximum observations per regressor: 10,000;
- maximum requested backtest models: 16; and
- positive, bounded backtest horizon, initial window, and step.

## Output and diagnostic contract

Public results are validated before serialization:

- forecast timestamps must increase and match the requested horizon;
- forecast and causal-impact values must be finite;
- backtest folds must have matching actual/forecast lengths;
- MAE and RMSE must be finite;
- MAPE is `null` when any actual denominator is zero;
- p-values, when present, must be finite and between zero and one;
- diagnostics must be bounded, JSON-compatible, use string keys, and contain no non-finite numeric values.

The API does not serialize `NaN` or infinity.

## Service examples

### Forecast

```python
from apps.api.services.forecast_service import ForecastService

service = ForecastService()
result = service.forecast_series(
    series=historical_data,
    horizon=30,
    model="arima",
    exogenous={"fx_rate": fx_series},
)
```

### Rolling backtest

```python
results = service.backtest(
    historical_data,
    horizon=7,
    models=["arima", "gradient_boosting"],
    initial_window=30,
    step=7,
)
```

### Causal impact

```python
impact = service.causal_impact(
    historical_data,
    event_start="2024-07-01",
    event_end="2024-07-14",
    interventions={"campaign": campaign_dummy_series},
    model="arima",
)
```

The intervention window must be ordered and fully contained within the target series.

## API endpoints

Every forecast route requires an active persisted access-token session and tenant membership for `organization_id`. Authorization occurs before model discovery or forecast work.

### `POST /forecast/series`

```json
{
  "organization_id": 1,
  "series": [["2024-01-01", 100.0], ["2024-01-02", 105.0]],
  "horizon": 2,
  "model": "arima",
  "regressors": {
    "fx_usd_eur": [["2024-01-01", 0.91], ["2024-01-02", 0.92]]
  }
}
```

The route requires at least as many target observations as the requested horizon.

### `GET /forecast/models?organization_id={id}`

Returns the bounded model registry and optional-dependency availability after tenant authorization.

### `POST /forecast/backtest`

Runs bounded rolling-origin evaluation for the requested models and returns ordered folds plus aggregate metrics.

### `POST /forecast/impact`

Returns bounded counterfactual-versus-observed points for a contained intervention window.

## Error behavior

Expected validation failures return a controlled `400` detail from a bounded allowlist. Unknown model-library exceptions return a generic `400` response. Server logs record only the forecast operation and exception type; they do not include raw exception text, request payloads, regressors, credentials, or tenant data.

Pydantic request-shape and hard-limit failures continue to use the standard `422` response.

## Testing policy

Required forecast tests are hermetic and cover:

- target, regressor, intervention, output, metric, and diagnostic non-finite values;
- duplicate resolution and sorted input;
- one-point, two-point, regular daily/hourly, and irregular cadence;
- spring-forward and fall-back timezone behavior;
- mixed timezone rejection and regressor alignment;
- constant, negative, and zero-heavy data;
- MAPE zero-denominator behavior;
- model unavailability and unsupported models;
- tenant-first API execution; and
- sanitized service and API failures.

No required test downloads models, uses provider credentials, or makes live network calls.

## Known limits

- Forecast quality depends on the supplied data and model assumptions.
- Prophet remains optional and is not installed by the base requirements.
- Future exogenous observations are not accepted as a separate request surface; the current engine carries forward the final validated regressor row.
- The service does not perform automated model governance, approval, or accounting posting.
