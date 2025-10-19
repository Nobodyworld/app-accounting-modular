# Repo Intelligence Report

## System Overview
- **Domain scope**: Modular general ledger with budgeting, forecasting, FX, market data, tax, and workflow automation.
- **Runtime services**:
  - `apps/api`: FastAPI service exposing REST endpoints for auth, audit, ledger, FX, market, tax, forecasting, reporting, and workflow orchestration.
  - `apps/web`: Streamlit dashboard consuming the API for reporting and operational workflows.
  - `apps/api/scheduler.py`: APScheduler instance refreshing forecasts and synchronising providers on a cron.
- **Supporting surfaces**:
  - `cli/macli.py`: Click-based CLI for bootstrapping accounts, running ingest jobs, and invoking reports.
  - `plugins/`: Provider contracts and first-party implementations (ECB FX, Yahoo market data, OECD tax stub).
  - `docs/`: Architecture and domain documentation for contributors.
- **Data flow**:
  1. Requests hit FastAPI routers (`apps/api/routers/*`) → services (`apps/api/services/*`) → SQLModel persistence (`apps/api/db.py`).
  2. Scheduler jobs reuse services for periodic refreshes and audit logging.
  3. Streamlit app authenticates via API, fetches reports, and renders dashboards.
  4. CLI shares configuration and service layer to seed data or trigger workflows.
- **External interfaces**: RESTful JSON API, Streamlit UI, CLI commands. No public gRPC/GraphQL. Docker Compose for local deployment.

## Tech Stack Map
- **Languages**: Python 3.11 (FastAPI, SQLModel, Streamlit), SQL for persistence (SQLite by default).
- **Frameworks/Libraries**: FastAPI, SQLModel, Pydantic v2, APScheduler, Passlib, HTTPX, Requests, Pandas/NumPy, Streamlit.
- **Tooling**: Ad-hoc Black/Ruff config (no automation), pytest test suite, docker-compose for local stack.
- **Dependencies**:
  - Core runtime pinned in `requirements.txt`; lacks lock file and separation of prod/dev extras.
  - Streamlit pulls large transitive surface (watch performance/security).
- **Module coupling**:
  - Services tightly coupled to SQLModel session helpers; minimal interface abstraction.
  - Scheduler imports services directly (process-global state, limited test seam).
  - Plugins discovered via registry module, no dynamic entry points.

## Hotspots & Dead Code
- **High churn / complexity**: `apps/api/services/*` (ledger, forecast, workflow) combine business rules, IO, and background coordination.
- **Observation gaps**: Minimal structured logging; scheduler swallows exceptions; lack of request tracing.
- **Potential dead code**:
  - `apps/api/audit.py` `AuditAction.EVENT` enumeration unused across repo.
  - Unreferenced docs (`docs/AI_INTERFACE.md`) describing non-existent integration—candidate for archival or implementation.
- **Test blind spots**: Streamlit smoke test only ensures import; no contract tests for API schema or CLI behaviors beyond basics.

## Risks & Quick Wins
1. **Absence of CI/CD** – No automated tests or lint in CI; high risk of regressions → *Quick win*: introduce GitHub Actions with lint/test matrix.
2. **Configuration entropy** – No `.env.example`, weak default secrets, limited validation → *Quick win*: centralise settings, validate, and document.
3. **Lack of security posture** – Missing SECURITY.md, Code of Conduct, reporting process → *Quick win*: add governance docs.
4. **Scheduler resilience** – Exceptions swallowed; jobs share global session → *Medium effort*: add logging, retries, dependency injection.
5. **Typing gaps** – Targeted strict mypy now covers settings and forecasting modules; remaining services still rely on implicit `Any` from SQLModel → *Medium effort*: expand coverage and add SQLModel-aware plugins.
6. **Dependency freshness** – No Renovate or update policy; risk of vulnerable packages → *Quick win*: add Renovate config and SBOM pipeline.
7. **Test coverage** – Integration coverage moderate but lacks API schema validation and CLI/e2e depth → *Medium effort*: add contract & e2e tests.
8. **Observability** – Minimal metrics/logging/tracing; scheduler silent failures → *Larger effort*: adopt OpenTelemetry/logging strategy.
9. **Release hygiene** – No release automation, changelog manual → *Medium effort*: adopt semantic-release workflow.
10. **Monolith boundaries** – Services mix domain logic with persistence; hindered testability → *Long-term*: refactor toward layered architecture.

## Top Opportunities by ROI
1. **Establish CI with lint/test matrix** (High impact, Low effort).
2. **Adopt pre-commit with formatter/linter hooks** (High impact, Low effort).
3. **Add governance docs & templates** (Medium impact, Low effort).
4. **Introduce mypy/pyright and fix critical typing issues** (High impact, Medium effort).
5. **Harden config with `.env.example` and validation** (High impact, Medium effort).
6. **Add SBOM & dependency audit workflow** (Medium impact, Medium effort).
7. **Implement structured logging & scheduler instrumentation** (High impact, Medium effort).
8. **Enhance API contract tests & docs (OpenAPI validation)** (Medium impact, Medium effort).
9. **Modularise services into domain interfaces** (High impact, High effort).
10. **Containerize with multi-stage build & CD pipeline** (High impact, Medium/High effort).
