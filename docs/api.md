# API Reference

This document provides an overview of the Modular Accounting REST API endpoints. For detailed OpenAPI specifications, visit `/docs` when the API is running.

## Base URL
```
http://localhost:8000
```

## Authentication
Most endpoints require authentication. See the security documentation for details.

## Core Endpoints

### Health & Monitoring
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe with subsystem status
- `GET /health/metrics` - Prometheus metrics
- `GET /health/telemetry` - Aggregated observability data

### Snapshots
- `POST /snapshot` - Create a data snapshot
- `POST /snapshot/scenarios` - Execute batch scenario snapshots
- `POST /snapshot/plans/preview` - Preview scenario plans

### Extensions
- `GET /extensions` - List loaded extensions
- `GET /extensions/contracts` - Get extension automation contracts

### Data Providers
- `GET /fx/rates` - Foreign exchange rates
- `GET /market/quotes` - Market data quotes
- `GET /commodity/quotes` - Commodity price quotes
- `GET /tax/rules` - Tax rules by jurisdiction

### Ledger
- `GET /ledger/accounts` - List accounts
- `POST /ledger/accounts` - Create account
- `GET /ledger/transactions` - List transactions
- `POST /ledger/transactions` - Record transaction
- `GET /ledger/balance` - Account balances

### Reports
- `GET /reports/pnl` - Profit & Loss report
- `GET /reports/balance-sheet` - Balance sheet report
- `GET /reports/tax-summary` - Tax summary report

### Forecasting
- `POST /forecast` - Generate forecast
- `GET /forecast/models` - List available models

### Audit
- `GET /audit/snapshot` - Generate audit snapshot
- `GET /audit/reports` - List audit reports

## Request/Response Format

All endpoints accept and return JSON. Dates are in ISO 8601 format, amounts use the `Money` schema with currency codes.

### Example Request
```json
{
  "base_currency": "USD",
  "commodity_symbols": ["XAU", "XAG"],
  "jurisdictions": ["US"]
}
```

### Example Response
```json
{
  "fx_rates": [...],
  "commodity_quotes": [...],
  "tax_rules": [...],
  "diagnostics": {...},
  "cache_stats": {...}
}
```

## Error Handling

Errors return standard HTTP status codes with JSON error details:

```json
{
  "detail": "Error description",
  "error_code": "SPECIFIC_ERROR"
}
```

## Rate Limiting

API endpoints implement rate limiting. Check response headers for limit information.

## WebSocket Support

Real-time updates are available via WebSocket at `/ws/updates`.

## SDKs & Clients

- **Python**: Use the `DataSnapshotService` directly
- **CLI**: `macli` commands for programmatic access
- **OpenAPI**: Generate clients from `/openapi.json`

See the [examples](examples.md) for integration code samples.