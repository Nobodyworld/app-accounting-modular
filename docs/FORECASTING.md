# Forecasting

Modular Accounting includes forecasting capabilities for time series prediction, supporting both baseline statistical models and advanced techniques with external regressors.

## Overview

The forecasting system provides:

- **Baseline Models**: ARIMA with automatic order selection
- **Advanced Models**: Support for exogenous regressors (events, FX rates, commodities)
- **API Integration**: REST endpoints for forecast generation
- **Extensibility**: Plugin architecture for custom forecasting models

## ForecastService

The core forecasting service supports multiple algorithms:

### ARIMA Baseline

Automatic ARIMA model selection with seasonal decomposition:

```python
from apps.api.services.forecast import ForecastService

service = ForecastService()
forecast = service.forecast_arima(
    series=historical_data,
    horizon=30,
    seasonal=True
)
```

### Exogenous Regressors

Incorporate external factors like market events or economic indicators:

```python
forecast = service.forecast_with_regressors(
    series=historical_data,
    regressors={
        'fx_rate': fx_series,
        'commodity_price': commodity_series,
        'events': event_dummies
    },
    horizon=30
)
```

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
  }
}
```

Response:
```json
{
  "forecast": [[timestamp, predicted_value], ...],
  "model_info": {
    "type": "arima",
    "order": [1, 1, 1],
    "seasonal_order": [0, 1, 1, 12]
  },
  "confidence_intervals": [[timestamp, lower, upper], ...]
}
```

### List Available Models

**GET** `/forecast/models`

Returns available forecasting models and their capabilities.

## Model Types

### ARIMA (AutoRegressive Integrated Moving Average)

- **Use Case**: Baseline forecasting for stationary or seasonally adjusted series
- **Parameters**: Automatically selected p, d, q orders
- **Seasonal Support**: SARIMA for seasonal patterns

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

The forecasting system includes evaluation metrics:

- **MAE**: Mean Absolute Error
- **RMSE**: Root Mean Square Error
- **MAPE**: Mean Absolute Percentage Error
- **Backtesting**: Rolling window validation

## Future Enhancements

- Advanced models (Prophet, LSTM)
- Causal impact analysis
- Automated model selection
- Forecast combination techniques
- Real-time forecast updates

See TASKLIST.md for detailed tracking of forecasting improvements (TASK-0011 through TASK-0015).
