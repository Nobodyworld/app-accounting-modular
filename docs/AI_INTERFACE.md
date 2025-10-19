# AI Interface Guide

This document summarises the structured entry points that agent frameworks can call when integrating with Modular Accounting.

## REST API Surface
- **Base URL:** `https://{host}/` (default `http://localhost:8000` in development).
- **Authentication:** Bearer tokens issued via `POST /auth/token` (requires username/password). Tokens expire based on `MODACCT_ACCESS_TOKEN_EXPIRE_MINUTES`.
- **Core Endpoints:**
  - `GET /core/health` – readiness/liveness probe (no auth).
  - `GET /providers` family – discover configured FX, market, and tax providers.
  - `POST /ledger/accounts` – create ledger accounts (requires organization context).
  - `POST /ledger/transactions` – post double-entry transactions.
  - `GET /reports/trial-balance` – fetch balances for an organization.
  - `POST /forecast/refresh` – trigger budget forecast refresh.

The FastAPI application exposes an OpenAPI schema at `/openapi.json` suitable for dynamic agent ingestion.

## Authentication Flow for Agents
1. Obtain credentials for a service account stored securely (e.g., Vault).
2. Request an access token via `/auth/token`.
3. Include the header `Authorization: Bearer <token>` and the organization scoping headers (`X-Organization-ID`) as required by routers.
4. Handle HTTP 429 responses from `/auth/token` by backing off exponentially.

Every authentication attempt is written to the audit log (`AuditAction.ACCESS`), making usage traceable.

## Scheduler & Automation Hooks
- Forecast refreshes are scheduled in-process using APScheduler. Agents can query `GET /reports/status` (planned) or trigger manual runs when necessary.
- The scheduler start/stop lifecycle is idempotent, enabling agent-driven API restarts without duplicate cron jobs.

## CLI Automation
The `cli/` package exposes Typer commands (see `cli/__main__.py`) that agents can invoke via subprocess for maintenance tasks such as database seeding or plugin syncs.

## Extending via Plugins
Custom data sources can be registered by implementing the provider protocols in `apps/api/services/*_service.py` and placing the module under `plugins/`. Agents can then select providers via API parameters.

## Response Schemas
All responses rely on Pydantic v2 schemas declared in `apps/api/schemas.py`. Agents should expect standard FastAPI validation errors (`422`) with field-level details.

## Observability
- Structured authentication logs are emitted via the Python logging subsystem.
- Persistent audit entries can be fetched via `GET /audit/logs` with pagination (planned enhancement).

For tighter integrations (LangChain, MCP, AgentKit), wrap the REST endpoints or CLI commands described above into tool declarations referencing this schema.
