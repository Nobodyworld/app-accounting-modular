# Forecasting

`ForecastService` supports:
- ARIMA baseline with automatic order selection (# TODO: refine)
- Optional exogenous regressors from events, FX, commodities (# TODO)

API:
- `POST /forecast/series` body: { "series": [[ts, value], ...], "horizon": 30 }
- returns: { "forecast": [[ts, yhat], ...] }

# TODO
- Prophet or advanced ML regressors
- Causal impact analysis with event interventions
- Backtesting harness & model registry
