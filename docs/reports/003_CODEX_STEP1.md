# Codex Chain – Step 1: Comprehend & Map

## Repository purpose & domain focus
- **Mission**: Provide a modular accounting toolkit that stitches together tax, FX, and commodity data sources through interchangeable adapters so teams can assemble finance workflows without a heavyweight stack.【F:README.md†L1-L27】
- **Domain primitives**: Rich dataclasses encapsulate currencies, FX rates, commodities, tax rules, and ledger transactions used across services and adapters.【F:src/apps/modular_accounting/domain/models.py†L11-L171】

## Core modules & architectural intent
- **Domain & application layers**: Ports define provider contracts while the `DataSnapshotService` orchestrates FX, commodity, and tax fetches into immutable payloads for higher layers.【F:src/apps/modular_accounting/domain/ports.py†L11-L33】【F:src/apps/modular_accounting/application/snapshots.py†L12-L99】
- **Adapters & CLI**: In-memory adapters plus a Click-powered demo CLI demonstrate snapshot creation and JSON emission for quick experiments.【F:src/apps/modular_accounting/adapters/in_memory.py†L11-L92】【F:src/cli/demo_cli.py†L47-L131】
- **API surface**: A FastAPI application wires routers for audit, ledger, FX, market, tax, forecasts, and workflow domains while injecting observability middleware and scheduler lifecycles.【F:src/apps/api/main.py†L24-L72】
- **Plugin ecosystem**: Provider metadata and instantiation flow through a cached loader that validates required capabilities, enabling swappable integrations configured at runtime.【F:src/apps/api/services/plugin_loader.py†L13-L178】
- **Observability**: Structured logging utilities propagate correlation IDs across HTTP, jobs, and CLI contexts for consistent telemetry.【F:src/apps/observability/logging.py†L1-L167】
- **UI layer**: A Streamlit console consumes API endpoints for health, budgeting, cashflow, and data sync operations, rounding out the DX story.【F:src/apps/web/app.py†L1-L120】

## Feature map & data flow
1. **Data ingestion**: Domain ports define required provider methods, and adapters implement them (in-memory, plugins, or remote services).【F:src/apps/modular_accounting/domain/ports.py†L11-L33】【F:src/apps/modular_accounting/adapters/in_memory.py†L11-L92】
2. **Snapshot orchestration**: `DataSnapshotService` normalises incoming request scope and collates FX, commodity, and tax records into deterministic tuples.【F:src/apps/modular_accounting/application/snapshots.py†L35-L99】
3. **Service exposure**: FastAPI routers, Streamlit dashboards, and CLI commands all consume the same orchestration layer, ensuring consistent behaviour across interfaces.【F:src/apps/api/main.py†L24-L68】【F:src/cli/demo_cli.py†L47-L131】【F:src/apps/web/app.py†L1-L120】
4. **Plugin loading**: Runtime configuration enumerates allowable providers; loaders validate capability-specific methods before exposing metadata or instances to services and background jobs.【F:src/apps/api/services/plugin_loader.py†L53-L178】
5. **Testing**: Pytest suites exercise snapshot orchestration, API routers, schedulers, and plugin logic to prevent regressions across the stack.【F:tests/test_data_snapshot_service.py†L1-L176】

## Dependency surface
- **Core stack**: FastAPI + Uvicorn for HTTP, Pydantic/SQLModel for schema & persistence, APScheduler for jobs, and Streamlit for the console UI.【F:requirements.txt†L1-L12】
- **Analytics & finance tooling**: Pandas, NumPy, statsmodels, and yfinance back reporting, forecasting, and market data synchronisation.【F:requirements.txt†L7-L11】
- **Security & integration**: Passlib, python-jose, requests/httpx, and python-multipart cover auth flows, REST calls, and form uploads.【F:requirements.txt†L6-L17】

## Documentation status
- **Top-level README** gives mission, component overview, and usage walkthroughs.【F:README.md†L1-L36】
- **Docs folder** hosts setup, adapter guidance, examples, and roadmap references linked from the index.【F:docs/index.md†L1-L8】
- **Governance files** (CODE_OF_CONDUCT, CONTRIBUTING, SECURITY, SUPPORT) already exist at the root for contributor onboarding.【F:CONTRIBUTING.md†L1-L37】

## Known pain points & TODOs
- Outstanding tasks include shipping real provider packages, expanding snapshot/CLI edge-case tests, and delivering persistence examples for ledger integrations (tracked via TASK-0001 through TASK-0003).
- API startup lacks structured failure logging hooks, called out as a TODO in the main application factory (tracked via TASK-0083).【F:src/apps/api/main.py†L1-L87】
- Plugin caching requires manual invalidation when provider configuration changes, relying on explicit refresh calls to avoid stale metadata (tracked via TASK-0080 and TASK-0084).【F:src/apps/api/services/plugin_loader.py†L53-L178】
