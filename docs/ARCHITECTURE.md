# Architecture

The Modular Accounting platform is organised around a layered service architecture with strict separation between transport, domain logic, and integrations. This document sketches the moving pieces so new contributors can reason about data flow and extension points quickly.

## High-Level Topology
```mermaid
graph TD
    subgraph UI
        Streamlit[Streamlit Console]
    end
    subgraph API
        Router[FastAPI Routers]
        Services[Domain Services]
        Scheduler[APScheduler Jobs]
    end
    subgraph Data
        DB[(SQLModel / Database)]
        Plugins{{Plugin Providers}}
    end

    Streamlit <--> Router
    CLI[CLI (Click)] --> Router
    Scheduler --> Services
    Router --> Services
    Services --> DB
    Services --> Plugins
```

- **UI Layer (`apps/web`)** – Streamlit dashboards render ledger, forecast, and report data from the API.
- **Transport Layer (`apps/api/routers`)** – FastAPI routers expose REST endpoints and enforce authentication/authorisation via dependencies in `apps/api/security.py` and `apps/api/dependencies.py`.
- **Domain Layer (`apps/api/services`)** – Business logic for ledgering, FX, market data, tax, budgeting, and workflows. Services persist via SQLModel models defined in `apps/api/models/`.
- **Integration Layer (`plugins/`)** – Dynamically loaded providers offering FX rates, market quotes, or tax rules. See [docs/PLUGINS.md](PLUGINS.md).
- **Observability (`apps/observability/logging.py`)** – Structured logging middleware and context managers reused by API, scheduler, and CLI entrypoints.

## Request Lifecycle
1. **HTTP Request** arrives at `apps/api/main.py` → `FastAPI` app.
2. **Router Dependency Resolution** wires security (`get_current_user`), sessions (`session_with_audit_context`), and audit metadata.
3. **Service Invocation** performs domain logic (e.g., `LedgerService.post_transaction`).
4. **Persistence** writes via SQLModel within a scoped session from `apps/api/db.py`.
5. **Response Serialization** uses Pydantic models from `apps/api/schemas.py` and metadata helpers in `apps/api/utils/metadata.py`.
6. **Logging/Audit** – request context middleware stamps logs; audit actions write via `apps/api/audit.py` where relevant.

## Scheduler Lifecycle
- Defined in `apps/api/scheduler.py` using APScheduler.
- Started/stopped via the FastAPI lifespan context in `apps/api/main.py` to prevent duplicate job registration during reloads.
- Jobs typically call service methods (e.g., `FXService.sync`) with a dedicated audit actor for traceability.

## Plugin Discovery Flow
```mermaid
graph LR
    Settings[Configuration Allow List] --> Loader[plugin_loader.available_providers]
    Loader --> Importer[Dynamic import of plugins.<name>.provider]
    Importer --> Handle[ProviderHandle(metadata, instance_factory)]
    Handle --> Services
    Services -->|calls| Providers[Provider Instances]
```

1. Configuration selects provider keys (environment variables or database entries).
2. `available_providers()` enumerates plugin metadata and ensures providers expose the required factory.
3. Services request providers via `load_provider()` which returns a handle containing metadata and a cached instance.
4. Provider instances implement domain-specific protocols (FX, market, tax) expected by their respective services.

## Data Model Highlights
- **Ledger** – `Account`, `Transaction`, `JournalEntry`, and `StagedTransaction` tables capture double-entry bookkeeping.
- **Market/FX** – `Instrument`, `Price`, and `Rate` store time-series data sourced from plugins.
- **Forecasting/Budget** – `ForecastPlan`, `ForecastOutput`, `Budget`, and `BudgetLine` persist modelling inputs and outputs.
- **Audit** – `AuditLog` captures CRUD/audit events with actor metadata derived from request headers or CLI contexts.

Refer to `apps/api/models/models.py` for full SQLModel definitions.

## Deployment Considerations
- **Local Development** – SQLite, Uvicorn reload, Streamlit dev server. Use `.env` to supply secrets.
- **Production** – Recommend Postgres, systemd or container orchestration, and centralised logging sinks. Ensure `MODACCT_JWT_SECRET_KEY` is configured and rotate tokens via external automation.
- **Scalability** – Scale API horizontally; scheduler should run in a single instance or use distributed job stores. Consider extracting long-running jobs into workers backed by a message queue in future iterations.

## Related Reading
- [CONFIGURATION.md](CONFIGURATION.md) for environment variables and security controls.
- [PLUGINS.md](PLUGINS.md) for integration lifecycle details.
- [FORECASTING.md](FORECASTING.md) for modelling-specific architecture.
