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
- `POST /ledger/account` - Create a tenant account
- `POST /ledger/post` - Record a balanced tenant transaction; dates in closed periods return `409` with `ACCOUNTING_PERIOD_CLOSED`
- `GET /ledger/trial-balance` - Return tenant trial-balance rows and totals

### Reports
- `GET /reports/budget-vs-actual` - Tenant-scoped budget variance report used by close reviews
- `GET /reports/cashflow-forecast` - Tenant-scoped cashflow report

### Forecasting
- `POST /forecast` - Generate forecast
- `GET /forecast/models` - List available models

### Audit
- `GET /audit/` - Administrator-only tenant audit log with bounded pagination

### Accountant close workspace

Every route below requires a persisted access-token session and `organization_id`. Reads require tenant membership. Operational mutations require ledger-manager or administrator membership. Final close, reopen, cancellation, final checklist approval, and approval revocation require an administrator. Scoped objects from another tenant return a nondisclosing `404` after organization authorization.

- `POST|GET /close/periods` and `GET /close/periods/{period_id}`
- `POST|GET /close/periods/{period_id}/cycles` and `GET /close/cycles/{cycle_id}`
- `POST /close/cycles/{cycle_id}/{start|ready|close|reopen|cancel}`
- `GET /close/cycles/{cycle_id}/readiness`
- `GET|POST /close/cycles/{cycle_id}/checklist`
- `PATCH /close/cycles/{cycle_id}/checklist/{task_id}`
- `GET|POST /close/cycles/{cycle_id}/reconciliations`
- `PATCH /close/cycles/{cycle_id}/reconciliations/{reconciliation_id}`
- `POST /close/cycles/{cycle_id}/reconciliations/{reconciliation_id}/approve`
- `POST /close/cycles/{cycle_id}/variance-reviews/from-budget`
- `GET /close/cycles/{cycle_id}/variance-reviews`
- `PATCH /close/cycles/{cycle_id}/variance-reviews/{review_id}`
- `GET|POST /close/cycles/{cycle_id}/journal-approvals`
- `POST /close/cycles/{cycle_id}/journal-approvals/{approval_id}/decide`
- `GET /close/cycles/{cycle_id}/evidence/preview`
- `POST /close/cycles/{cycle_id}/evidence`
- `GET /close/cycles/{cycle_id}/evidence/download`

Reconciliation uses the explicit sign convention `difference = control_balance - ledger_ending_balance`. The ledger balance is server-derived from persisted journal entries through the inclusive period end. Evidence ZIPs contain canonical JSON and LF-terminated spreadsheet-safe CSV with deterministic filenames, row ordering, ZIP timestamps, per-file SHA-256 values, and a returned manifest SHA-256.

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
