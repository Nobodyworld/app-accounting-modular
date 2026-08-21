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
- `GET /providers?organization_id={id}` - Member-visible trusted/effective catalog
- `GET /providers/{provider_key}?organization_id={id}` - Safe conformance and governance detail
- `GET /providers/policies?organization_id={id}` - Organization policies and effective defaults
- `PUT /providers/{provider_key}/policy?organization_id={id}` - Administrator enable/disable mutation with `expected_revision`
- `PUT|DELETE /providers/defaults/{capability}?organization_id={id}` - Administrator default mutation/clearing with revision protection
- `GET /providers/{provider_key}/credentials?organization_id={id}` - Manifest variable names plus presence booleans only
- `GET /providers/evidence/{preview|export}?organization_id={id}` - Deterministic bounded governance evidence
- `GET /fx/rates` - Foreign exchange rates
- `GET /market/quotes` - Market data quotes
- `GET /commodity/quotes` - Commodity price quotes
- `GET /tax/rules` - Tax rules by jurisdiction

Provider reads require a persisted session and organization membership; mutations require organization administrator authority. Tenant requests cannot submit module, factory, package, wheel, or registry paths. Explicit FX, market, tax, and snapshot provider keys are resolved only after tenant authorization and must be effective for that organization. Errors use bounded `404`, `409`, or validation responses without disclosing cross-tenant rows, environment values, loader exceptions, or raw provider bodies.

These contracts describe authenticated tenant API operations. The public/local Streamlit Snapshot Review does not call `/providers` or the tenant `/snapshot` route; it uses only the local process-trusted catalog and `SnapshotOrchestrator`, without organization policy/defaults.

### Ledger
- `POST /ledger/account` - Create a tenant account
- `POST /ledger/post` - Record a balanced tenant transaction; dates in closed periods return `409` with `ACCOUNTING_PERIOD_CLOSED`, and dates in a cycle awaiting approval return `409` with `ACCOUNTING_PERIOD_CLOSE_READY`
- `GET /ledger/trial-balance` - Return tenant trial-balance rows and totals

### Reports
- `GET /reports/budget-vs-actual` - Tenant-scoped budget variance report used by close reviews
- `GET /reports/cashflow-forecast` - Tenant-scoped cashflow report

### Forecasting

Every route below requires an active persisted access-token session and tenant membership for `organization_id`. Authorization occurs before model discovery or forecast work.

- `POST /forecast/series` - Generate a bounded forecast. Target values, regressors, predictions, and diagnostics must be finite. Exact duplicate timestamps use the last supplied value. Multi-point series must use a regular cadence.
- `GET /forecast/models?organization_id={id}` - Return the bounded model registry and optional-dependency availability.
- `POST /forecast/backtest` - Run bounded rolling-origin evaluation with finite MAE/RMSE and nullable MAPE when an actual denominator is zero.
- `POST /forecast/impact` - Evaluate an ordered intervention window fully contained within the target series.

Forecast timestamps cannot mix naive and timezone-aware values. All aware values use one timezone; regressors and interventions must use the target timezone and align to the target timeline. Daily and hourly local cadence remains timezone-aware across daylight-saving transitions. Expected validation failures return a bounded sanitized `400` detail. Unknown model-library failures return a generic `400` without raw exception text or request payloads in the response or logs. Request-shape and centralized hard-limit failures remain standard `422` responses. See [`FORECASTING.md`](FORECASTING.md) for the complete finite-value, duplicate, cadence, timezone, output, and diagnostic contracts.

### Audit
- `GET /audit/` - Administrator-only tenant audit log with bounded pagination

### Accountant close workspace

Every route below requires a persisted access-token session and `organization_id`. Reads require tenant membership. Operational mutations require ledger-manager or administrator membership. Final close, reopen, cancellation, restart, return-to-work, and approval revocation require an administrator. The final checklist approval is never manually writable. Scoped objects and assignment users from another tenant return a nondisclosing `404` after organization authorization.

- `POST|GET /close/periods` and `GET /close/periods/{period_id}`
- `POST|GET /close/periods/{period_id}/cycles` and `GET /close/cycles/{cycle_id}`
- `POST /close/cycles/{cycle_id}/{start|ready|return-to-work|close|reopen|cancel|restart}`
- `GET /close/cycles/{cycle_id}/readiness`
- `GET|POST /close/cycles/{cycle_id}/checklist`
- `PATCH /close/cycles/{cycle_id}/checklist/{task_id}`
- `GET|POST /close/cycles/{cycle_id}/reconciliations`
- `PATCH /close/cycles/{cycle_id}/reconciliations/{reconciliation_id}`
- `POST /close/cycles/{cycle_id}/reconciliations/{reconciliation_id}/approve`
- `POST /close/cycles/{cycle_id}/variance-reviews/from-budget`
- `GET /close/cycles/{cycle_id}/variance-reviews?limit=&offset=`
- `PATCH /close/cycles/{cycle_id}/variance-reviews/{review_id}`
- `GET /close/cycles/{cycle_id}/journal-approvals?limit=&offset=` and `POST /close/cycles/{cycle_id}/journal-approvals`
- `GET /close/cycles/{cycle_id}/journal-approvals/{approval_id}/history?limit=&offset=`
- `POST /close/cycles/{cycle_id}/journal-approvals/{approval_id}/decide`
- `GET /close/cycles/{cycle_id}/evidence/preview`
- `POST /close/cycles/{cycle_id}/evidence`
- `GET /close/cycles/{cycle_id}/evidence/download`

Reconciliation uses the explicit sign convention `difference = control_balance - ledger_ending_balance`. Cycle creation by a ledger manager uses server defaults. An administrator may supply only the typed policy fields for reconciliation scope/not-applicable status, variance requirement, and journal mode, and every override requires a bounded reason; unknown and inconsistent fields are rejected. Variance readiness requires the latest durable in-period run when enabled, including a zero-row run. Each rerun owns fresh rows, and only its current rows can be updated or affect readiness. Journal policy is explicit: `REQUESTED_ONLY` or `ALL_PERIOD_TRANSACTIONS`.

Reconciliation, variance, approval-summary, and decision-history reads use `limit`/`offset`, default to 100 records, and reject limits above 500. Approval summaries do not embed decision history. A separate tenant- and cycle-scoped history route returns the immutable decisions. A cycle may retain at most 500 approval records; an idempotent request for a current reference remains valid at the cap, while a new reference is rejected without partial state.

Operational writes are allowed only in `IN_PROGRESS`/`BLOCKED`; `READY_FOR_APPROVAL` freezes direct and workflow posting as well as close controls until an administrator records a reasoned return-to-work. `CLOSED` and `CANCELLED` are read-only except administrator reopen/restart. Every successful in-period post atomically advances `AccountingPeriod.ledger_activity_revision`. Approved reconciliations, the latest variance run, and evidence must match that revision. `CloseCycle.content_revision` independently tracks close-control mutations. Draft evidence conditionally verifies cycle status, close revision, and ledger revision at persistence time. `POST .../evidence` builds once and uses that one bundle for its response, durable `CloseEvidence` metadata, and generation audit. `GET .../evidence/download` returns `409 CLOSE_EVIDENCE_NOT_CURRENT` unless the latest tenant record matches the current cycle revision, ledger revision, draft/final classification, and recomputed manifest; it never records or silently regenerates evidence. Final close creates current `CLOSED` evidence in the same transaction. ZIPs contain only the latest variance run's current rows, durable run proof, immutable approval decisions, and a typed safe policy.

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
