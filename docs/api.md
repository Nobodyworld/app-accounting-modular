# API Reference

This document provides an overview of the Modular Accounting REST API endpoints. For detailed OpenAPI specifications, visit `/docs` when the API is running.

## Base URL
```
http://localhost:8000
```

## Authentication

Most endpoints require a bearer access token backed by an active persisted server session.

- `POST /auth/token` accepts the OAuth2 password form and returns `access_token`, `refresh_token`, `session_id`, and `token_type`.
- `POST /auth/refresh` accepts `{"refresh_token": "..."}` and rotates the access/refresh pair once while preserving `session_id`.
- `POST /auth/logout` requires the access bearer token and revokes its current session.
- `POST /auth/sessions/{session_id}/revoke?organization_id={id}` requires an authenticated administrator for the named organization and revokes only a session belonging to a member of that organization.

Access and refresh credentials are not interchangeable. Refresh reuse revokes the complete session. Authentication failures use a generic `401` response and do not disclose whether a claim, user, or persisted session caused rejection. See [`SECURITY.md`](SECURITY.md#authentication-session-lifecycle) for storage, cleanup, and client-handling details.

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

Login applies a process-local failure counter and five-minute lockout after five
failed attempts. It resets on restart and does not coordinate across workers or
hosts. The API does not provide general distributed rate-limit headers; LAN,
multi-worker, and public deployments require a shared edge or gateway control.

## WebSocket Support

Real-time updates are available via WebSocket at `/ws/updates`.

## SDKs & Clients

- **Python**: Use the `DataSnapshotService` directly
- **CLI**: `macli` commands for programmatic access
- **OpenAPI**: Generate clients from `/openapi.json`

See the [examples](examples.md) for integration code samples.
