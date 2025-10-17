# Forecasting

`ForecastService` and `BudgetService` support:
- ARIMA baseline with automatic order selection via AIC
- Extensible hooks for exogenous regressors (events, FX, commodities)
- Organization-aware budgeting models with ledger actual aggregation
- Artifact persistence (JSON, CSV) for pre-rendered budget vs actual and cashflow reports

API:
- `POST /forecast/series` body: { "series": [[ts, value], ...], "horizon": 30 }
- returns: { "forecast": [[ts, yhat], ...], "horizon": 30, "order": [p, d, q] }

Reports API:
- `GET /reports/budget-vs-actual?organization_id=<uuid>`
- `GET /reports/cashflow-forecast?organization_id=<uuid>`
- Both endpoints return structured results, metadata, and links to stored artifacts.

## Future Work
- Prophet or advanced ML regressors
- Causal impact analysis with event interventions
- Backtesting harness & model registry
