# AI & Automation Interface

Automation agents, workflow orchestrators, and AI copilots can interact with Modular Accounting through a small set of stable touch points. This guide consolidates authentication, REST usage, CLI wrappers, and observability expectations so external tooling can integrate safely.

## Base URL & Authentication
- **API base**: `http://localhost:8000/` during development (configure host/port per deployment).
- **Token endpoint**: `POST /auth/token` expects `application/x-www-form-urlencoded` credentials (`username`, `password`).
- **Headers**: include `Authorization: Bearer <token>` plus optional scoping headers (`X-Organization-ID`, `X-User-ID`, `X-Request-ID`) when calling protected endpoints. The `session_with_audit_context` dependency records these into the audit log.

Example token retrieval:
```bash
curl -X POST http://localhost:8000/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=agent@example.com&password=s3cret'
```

## Core REST Endpoints for Agents
| Capability | Endpoint | Notes |
| --- | --- | --- |
| Health checks | `GET /core/health` | unauthenticated readiness probe for orchestrators |
| Provider discovery | `GET /core/providers` | inspect available FX/market/tax providers before invoking sync commands |
| Ledger operations | `POST /ledger/transactions`, `GET /ledger/accounts` | scoped by organisation; expect validation errors (`422`) for imbalanced postings |
| Reporting | `GET /reports/trial-balance`, `GET /reports/cashflow-forecast` | return structured JSON with metadata links to artefacts |
| Forecasting | `POST /forecast/refresh`, `POST /forecast/series` | asynchronous refresh vs inline modelling |
| Audit access | `GET /audit/logs` (planned) | review structured audit entries once implemented |

The OpenAPI schema is exposed at `/openapi.json` and `/docs`. Agents can ingest the schema to generate strongly typed clients.

## CLI Automation
The Click-based CLI (`python -m cli.macli`) shares service implementations with the API. Useful commands for agents include:
```bash
python -m cli.macli sync-fx --base USD --provider ecb_reference_via_exchangerate_host
python -m cli.macli sync-prices AAPL --start 2024-01-01 --end 2024-01-31
python -m cli.macli ingest-ledger --file data/transactions.csv
```

Wrap CLI calls in subprocesses or job runners when REST endpoints do not yet expose the required workflow. CLI logging honours the same structured logging context (correlation IDs, request IDs) as the API.

## Observability Hooks
- Every authenticated request records an audit entry via `apps/api/audit.py`. Query the audit log (future endpoint) or inspect database tables to trace agent activity.
- Structured logs include `correlation_id`, `request_id`, and domain-specific metadata. Capture STDOUT/STDERR from CLI invocations to feed into your observability stack.
- Failed authentications emit warnings and audit records; implement exponential backoff on `401`/`429` responses to respect throttling limits.

## Extending the Platform
- **Plugins** – Implement provider contracts described in [PLUGINS.md](PLUGINS.md) to surface new FX/market/tax data for agents.
- **Webhooks** – For outward notifications, contribute router endpoints or background jobs that call out to your automation framework.
- **Custom APIs** – Add FastAPI routers under `apps/api/routers/` with appropriate dependencies; document them alongside agent workflows.

## Best Practices for Agent Builders
1. Cache the OpenAPI schema and refresh it periodically to detect contract changes.
2. Log request IDs returned in responses to correlate with server-side logs.
3. Handle pagination and rate limiting gracefully—future endpoints may introduce cursors and 429 responses.
4. Run integration tests against the local stack (via docker-compose or uvicorn) before deploying automations to production environments.
