# Forecasting & Budgeting Guide

The forecasting stack combines ARIMA-based time-series modelling with budgeting utilities to help finance teams project cashflow, revenue, and expense trends. This document summarises the involved services, API endpoints, CLI helpers, and diagnostics artefacts.

## Components
- **Service Layer** – `apps/api/services/forecast_service.py` orchestrates ARIMA modelling, confidence intervals, and diagnostic generation. `apps/api/services/budget_service.py` aggregates ledger actuals and budget lines for comparisons.
- **Routers** – `apps/api/routers/forecast.py` and `apps/api/routers/reports.py` expose public endpoints for generating forecasts and retrieving report artefacts.
- **Schemas** – Responses are typed via `apps/api/schemas.py` (`ForecastResponse`, `CashflowForecastResponse`, `BudgetVsActualResponse`).
- **Scheduler Jobs** – Periodic refreshes run via `apps/api/scheduler.py`, typically nightly, invoking `ForecastService.sync_latest` with configured horizons.

## API Usage
### Generate a Forecast Inline
```bash
curl -X POST http://localhost:8000/forecast/series \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
        "series": [["2024-01-01", 1200.0], ["2024-02-01", 1325.0]],
        "horizon": 6,
        "frequency": "MS"
      }'
```
Response payload (abridged):
```json
{
  "forecast": [["2024-03-01", 1411.2], ...],
  "confidence_intervals": {
    "lower": [...],
    "upper": [...]
  },
  "order": [1, 1, 1],
  "diagnostics": {
    "aic": 120.4,
    "bic": 125.0
  }
}
```

### Retrieve Budget vs Actual Report
```bash
curl "http://localhost:8000/reports/budget-vs-actual?organization_id=1" \
  -H 'Authorization: Bearer <token>'
```
The response includes summary rows, per-period breakdowns, and metadata describing generation timestamps and forecast parameters. Metadata normalisation occurs in `apps/api/utils/metadata.py` to ensure consistent types.

## CLI Helpers
The CLI mirrors scheduler workflows for manual intervention:
```bash
# Refresh all enabled forecast plans
python -m cli.macli forecast-refresh

# Export cached forecast artefacts to CSV
python -m cli.macli forecast-export --plan-id <uuid> --output forecasts.csv
```
(Refer to `cli/macli.py` for the latest command names and options.)

## Diagnostics Artefacts
Forecast runs persist additional artefacts for observability:
- **JSON Metadata** – Stored alongside reports detailing ARIMA order, horizon, training window, and provider context.
- **CSV Series** – Actual vs predicted series saved for offline analysis; accessible via the reports API metadata links.
- **Logs** – Structured logging records model summary statistics and any convergence warnings.

## Extending the Models
- Plug custom regressors or alternative algorithms by implementing strategy classes consumed by `ForecastService` (see TODO markers within the service).
- Adjust maximum horizons via `MODACCT_FORECAST_MAX_HORIZON` to prevent runaway compute on large plans.
- Integrate event-based signals by enabling the feature flag documented in [CONFIGURATION.md](CONFIGURATION.md).

## Roadmap
Future enhancements tracked in `PLAN.md` include:
- Introducing Prophet/NeuralProphet adapters alongside ARIMA.
- Backtesting harness with rolling-origin evaluation and benchmark comparisons.
- Model registry and versioning of artefacts for auditability.
