# Forecasting

`ForecastService` supports:
- ARIMA baseline with automatic order selection via AIC
- Extensible hooks for exogenous regressors (events, FX, commodities)

API:
- `POST /forecast/series` body: { "series": [[ts, value], ...], "horizon": 30 }
- returns: { "forecast": [[ts, yhat], ...], "horizon": 30, "order": [p, d, q] }

## Future Work
- Prophet or advanced ML regressors
- Causal impact analysis with event interventions
- Backtesting harness & model registry
