# Forecasting

`ForecastService` supports:

- ARIMA baseline with automatic order selection (see TASK-0011)
- Optional exogenous regressors from events, FX, commodities (see TASK-0012)

API:

- `POST /forecast/series` body: { "series": [[ts, value], ...], "horizon": 30 }
- returns: { "forecast": [[ts, yhat], ...] }

## Follow-up Work

Extended forecasting capabilities are catalogued in TASKSLIST.md as TASK-0013 through TASK-0015, spanning advanced regressors, causal impact analysis, and backtesting infrastructure.
