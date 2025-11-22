# Forecasting

Modular Accounting includes forecasting capabilities for time series prediction, supporting both baseline statistical models and advanced techniques with external regressors.

## Overview

The forecasting system provides:

- **Baseline Models**: ARIMA with automatic order selection
- **Advanced Models**: Prophet (optional dependency) and gradient boosting regressors with engineered seasonality
- **Event Awareness**: Exogenous regressors, intervention dummies, and causal impact analysis
- **Evaluation**: Rolling backtests with MAE/RMSE/MAPE diagnostics
- **API Integration**: REST endpoints for forecasts, causal impact, backtesting, and model discovery
- **Extensibility**: Plugin architecture for custom forecasting models

## ForecastService

The core forecasting service now supports multiple algorithms from a single entrypoint:

### ARIMA Baseline

```python
from apps.api.services.forecast_service import ForecastService

service = ForecastService()
forecast = service.forecast_series(
    series=historical_data,
    horizon=30,
    model="arima",
)
```

### Prophet and Advanced Regressors

Prophet is treated as an optional dependency; when installed it is available via the same dispatcher:

```python
forecast = service.forecast_series(
    series=historical_data,
    horizon=30,
    model="prophet",
    exogenous={
        "fx_rate": fx_series,
        "commodity_price": commodity_series,
        "events": event_dummies,
    },
)
```

### Gradient Boosting Regressor

A tree-based regressor with engineered seasonality and lagged features:

```python
forecast = service.forecast_series(
    series=historical_data,
    horizon=14,
    model="gradient_boosting",
    exogenous={"promo": promo_flags},
)
```

### Causal Impact Analysis

Estimate the lift or drag of an intervention window using a counterfactual baseline:

```python
impact = service.causal_impact(
    series=historical_data,
    event_start="2024-07-01",
    event_end="2024-07-14",
    interventions={"campaign": campaign_dummy_series},
    model="arima",
)
```

### Event NLP Helpers

Use `ForecastService.build_event_regressors` to convert event titles into
simple keyword-driven intensity scores that can be passed as exogenous
regressors for event-informed forecasts.

## API Endpoints

### Generate Forecast

**POST** `/forecast/series`

Request body:
```json
{
  "series": [[timestamp, value], ...],
  "horizon": 30,
  "model": "arima",
  "regressors": {
    "fx_usd_eur": [[timestamp, rate], ...],
    "event_impact": [[timestamp, dummy], ...]
  },
  "organization_id": 1
}
```

Response:
```json
{
  "forecast": [[timestamp, predicted_value], ...],
  "horizon": 30,
  "order": [1, 1, 1],
  "diagnostics": {
    "model": "arima",
    "mae": 0.1,
    "rmse": 0.2
  },
  "model": "arima",
  "timezone": "UTC"
}
```

### List Available Models

**GET** `/forecast/models`

Returns available forecasting models and their capabilities, including whether optional dependencies (like Prophet) are installed.

### Backtesting Harness

**POST** `/forecast/backtest`

Request:
```json
{
  "series": [[timestamp, value], ...],
  "horizon": 7,
  "models": ["arima", "gradient_boosting"],
  "regressors": {
    "fx_usd_eur": [[timestamp, rate], ...]
  },
  "initial_window": 30,
  "step": 7,
  "organization_id": 1
}
```

Response:
```json
[
  {
    "model": "arima",
    "metrics": {"mae": 0.2, "rmse": 0.3, "mape": 1.5},
    "tested_points": 21,
    "folds": [
      {
        "start": "2024-01-01T00:00:00",
        "end": "2024-01-21T00:00:00",
        "horizon": 7,
        "mae": 0.21,
        "rmse": 0.32,
        "mape": 1.6,
        "actual": [[timestamp, value], ...],
        "forecast": [[timestamp, predicted], ...]
      }
    ]
  }
]
```

### Causal Impact Analysis

**POST** `/forecast/impact`

Request:
```json
{
  "series": [[timestamp, value], ...],
  "event_start": "2024-07-01",
  "event_end": "2024-07-14",
  "interventions": {
    "campaign": [[timestamp, 0], [timestamp, 1], ...]
  },
  "model": "arima",
  "organization_id": 1
}
```

Response (counterfactual vs observed):
```json
{
  "model": "arima",
  "event_start": "2024-07-01T00:00:00",
  "event_end": "2024-07-14T00:00:00",
  "average_impact": 4.2,
  "cumulative_impact": 58.8,
  "p_value": 0.03,
  "points": [
    {
      "timestamp": "2024-07-03T00:00:00",
      "actual": 120.0,
      "predicted": 115.0,
      "impact": 5.0
    }
  ]
}
```

## Model Types

### ARIMA (AutoRegressive Integrated Moving Average)

- **Use Case**: Baseline forecasting for stationary or seasonally adjusted series
- **Parameters**: Automatically selected p, d, q orders
- **Seasonal Support**: SARIMA for seasonal patterns

### Prophet (Optional)

- **Use Case**: Seasonality-rich business series with holiday or event regressors
- **Parameters**: Automatic trend and seasonality detection; add regressors via `regressors` payload
- **Dependency**: Install `prophet>=1.0`; the API reports availability via `/forecast/models`.

### Gradient Boosting Regressor

- **Use Case**: Non-linear relationships with lagged effects and engineered seasonality
- **Parameters**: Lagged features (1/7/14 days) plus calendar sine/cosine terms
- **Dependency**: `scikit-learn` (shipped in base requirements)

### Regression with Exogenous Variables

- **Use Case**: Incorporating external factors (FX rates, commodity prices, events)
- **Parameters**: Lagged regressors, interaction terms
- **Event Integration**: Dummy variables for significant events

## Integration Examples

### Python Client

```python
import requests

response = requests.post('http://localhost:8000/forecast/series', json={
    'series': [[1640995200, 100.0], [1641081600, 105.0], ...],
    'horizon': 7,
    'model': 'arima'
})

forecast = response.json()['forecast']
```

### CLI Usage

```bash
# Forecast with historical data
python -m cli.macli forecast --series data.csv --horizon 30 --output forecast.json
```

## Evaluation and Backtesting

Use `/forecast/backtest` to run rolling-origin validation across one or more models. Metrics returned:

- **MAE**: Mean Absolute Error
- **RMSE**: Root Mean Square Error
- **MAPE**: Mean Absolute Percentage Error (ignored when actuals contain zeroes)
- **Fold Diagnostics**: Per-fold error metrics plus the forecast/actual pairs for inspection

## Future Enhancements

- Deep learning models (e.g., temporal convolution or LSTM variants)
- Automated model selection and blending
- Forecast combination techniques
- Real-time forecast updates

See TASKLIST.md for detailed tracking of forecasting improvements (TASK-0011 through TASK-0015).
