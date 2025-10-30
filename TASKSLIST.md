# TASKLIST: Agent Task Compilation Template

-*NEVER REMOVE TASK.md, TASKSLIST.md, REPORTS.md, or URGENT.md FROM THE ROOT*

Use this file to compile and track all tasks that need to be completed for this repository. Check off items as they are finished. Keep each task on a single line. Check off already completed tasks and keep things in chronological order when updating and adding to the file.

## Tasks Layout

- [ ] Task 1: Description of what needs to be done - Task Unique Identifier - When completed: Timestamp, Hyperlink to REPORT.md Task Report Unique Identifier
- [ ] Task 2: Description of what needs to be done - Task Unique Identifier - When completed: Timestamp, Hyperlink to REPORT.md Task Report Unique Identifier
- [ ] Task 3: Description of what needs to be done - Task Unique Identifier - When completed: Timestamp, Hyperlink to REPORT.md Task Report Unique Identifier

## Notes

*Add all additional context, blockers, or decisions made during task execution to REPORTS.md and include a link to the task and include a link to the report in this TASKLIST.md file.*

*This TASKLIST.md serves as the central hub for all repository work and should be kept up to date.*

*If consolidating todos and other task related files into this one, and there are completed tasks, use the date the file was last edited or created as the completion timestamp.*

*Add a TASK entry, as well as a Task Unique Identifier for hyperlinking to REPORTS.md.*

*Add a timestamp when completed and a hyperlink to the associated REPORTS.md entry.*

*Keep tasks in chronological order (Oldest First).*

## Active Tasks

- [ ] Publish concrete adapter packages for popular FX, tax, and commodity providers (Source: TODO.md) - TASK-0001 - When completed: _
- [ ] Add automated tests covering the demo CLI and snapshot service edge cases (Source: TODO.md) - TASK-0002 - When completed: _
- [ ] Provide persistence examples mapping domain transactions to external ledgers (Source: TODO.md) - TASK-0003 - When completed: _
- [ ] Re-run the dependency version audit once external package indexes are reachable (Source: TODO.md) - TASK-0004 - When completed: _
- [ ] Resolve mypy errors in `apps.observability` to satisfy strict configuration requirements (Source: TODO.md) - TASK-0005 - When completed: _
- [ ] Integrate `make audit` into CI and publish `REPORTS/audit-latest.md` artifacts (Source: TODO.md) - TASK-0006 - When completed: _
- [ ] Add strong typing for tax rule expressions, e.g., JSONLogic schemas (Source: docs/TAX_MODEL.md) - TASK-0007 - When completed: _
- [ ] Define a precedence and override strategy for layered tax rules (Source: docs/TAX_MODEL.md) - TASK-0008 - When completed: _
- [ ] Capture source provenance metadata for tax rules (Source: docs/TAX_MODEL.md) - TASK-0009 - When completed: _
- [ ] Build automated tax rule updaters for each jurisdiction (Source: docs/TAX_MODEL.md) - TASK-0010 - When completed: _
- [ ] Refine ARIMA auto-order selection for the forecasting service (Source: docs/FORECASTING.md & apps/api/services/forecast_service.py) - TASK-0011 - When completed: _
- [ ] Add exogenous regressors for events, FX, and commodities in forecasts (Source: docs/FORECASTING.md & apps/api/services/forecast_service.py) - TASK-0012 - When completed: _
- [ ] Introduce Prophet or other advanced ML regressors to forecasting (Source: docs/FORECASTING.md) - TASK-0013 - When completed: _
- [ ] Implement causal impact analysis with event interventions (Source: docs/FORECASTING.md) - TASK-0014 - When completed: _
- [ ] Build a backtesting harness and model registry for forecasting (Source: docs/FORECASTING.md) - TASK-0015 - When completed: _
- [ ] Secure and configure OpenExchangeRates API keys for FX providers (Source: docs/README.md) - TASK-0016 - When completed: _
- [ ] Add commodity and futures market data providers beyond `yfinance` (Source: docs/README.md) - TASK-0017 - When completed: _
- [ ] Integrate macroeconomic data sources such as FRED, WorldBank, or OECD (Source: docs/README.md) - TASK-0018 - When completed: _
- [ ] Implement an OECD VAT data puller for automated tax updates (Source: docs/README.md) - TASK-0019 - When completed: _
- [ ] Populate and maintain US Federal and State tax tables with regular updates (Source: docs/README.md) - TASK-0020 - When completed: _
- [ ] Deliver NLP and causal feature engineering for event-informed forecasts (Source: docs/README.md) - TASK-0021 - When completed: _
- [ ] Integrate bank feeds such as Plaid to unlock advanced reconciliation (Source: docs/README.md) - TASK-0022 - When completed: _
- [ ] Create a React-based web UI alternative alongside Streamlit (Source: docs/README.md) - TASK-0023 - When completed: _
- [ ] Simulate concurrent audit log writes to validate race condition handling (Source: tests/test_audit_logging.py) - TASK-0024 - When completed: _
- [ ] Add coverage for metadata update transitions once implemented (Source: tests/test_timezone_aware.py) - TASK-0025 - When completed: _
- [ ] Replace the temporary multipart stub when the lightweight dependency is selected (Source: tests/conftest.py) - TASK-0026 - When completed: _
- [ ] Validate async provider initialisation paths in the plugin loader (Source: tests/test_plugin_loader.py) - TASK-0027 - When completed: _
- [ ] Cover approval and rejection transitions via workflow API routes (Source: tests/test_workflow_api.py) - TASK-0028 - When completed: _
- [ ] Add multi-currency CSV import and FX lookup coverage to CLI tests (Source: tests/test_cli_import.py) - TASK-0029 - When completed: _
- [ ] Validate structured logging behaviour under multiprocessing executors (Source: tests/test_observability_logging.py) - TASK-0030 - When completed: _
- [ ] Extend ledger service tests to reversing entries and multi-organisation postings (Source: tests/test_ledger_service.py) - TASK-0031 - When completed: _
- [ ] Extend budget service tests with seasonal projection stress scenarios (Source: tests/test_budget_service.py) - TASK-0032 - When completed: _
- [ ] Add security integration coverage once lockouts share cache state (Source: tests/test_security_integration.py) - TASK-0033 - When completed: _
- [ ] Cover seasonal decomposition strategies in forecast service tests when available (Source: tests/test_forecast_service.py) - TASK-0034 - When completed: _
- [ ] Add multi-currency budget scenarios to reports API regression tests (Source: tests/test_reports_api.py) - TASK-0035 - When completed: _
- [ ] Exercise Streamlit interactions against a live API client abstraction (Source: tests/test_streamlit_app.py) - TASK-0036 - When completed: _
- [ ] Test metadata utilities with deeply nested array payloads (Source: tests/test_metadata_utils.py) - TASK-0037 - When completed: _
- [ ] Cover settings overrides for per-environment log destinations (Source: tests/test_config.py) - TASK-0038 - When completed: _
- [ ] Extend model schema constraint checks to workflow and audit tables (Source: tests/test_model_schema.py) - TASK-0039 - When completed: _
- [ ] Promote the workflow service helper to a shared fixture for reuse (Source: tests/test_workflow_service.py) - TASK-0040 - When completed: _
- [ ] Simulate distributed scheduler job runners once queue integration lands (Source: tests/test_scheduler.py) - TASK-0041 - When completed: _
- [ ] Remove the legacy alias from the OECD tax plugin stub after downstream migrations (Source: plugins/tax_oecd_stub/__init__.py) - TASK-0042 - When completed: _
- [ ] Introduce chunked commits for large workflow ingestion batches (Source: apps/api/services/workflow_service.py) - TASK-0043 - When completed: _
- [ ] Persist validation diagnostics from workflow ingestion for audit review (Source: apps/api/services/workflow_service.py) - TASK-0044 - When completed: _
- [ ] Validate currency consistency across postings before workflow commit (Source: apps/api/services/workflow_service.py) - TASK-0045 - When completed: _
- [ ] Surface accounts missing actuals within budget report metadata (Source: apps/api/services/budget_service.py) - TASK-0046 - When completed: _
- [ ] Apply currency conversion when aggregating multi-currency ledger data (Source: apps/api/services/budget_service.py) - TASK-0047 - When completed: _
- [ ] Stream large actual datasets instead of loading all rows into memory in budget services (Source: apps/api/services/budget_service.py) - TASK-0048 - When completed: _
- [ ] Implement provider-specific tax rule upsert logic (Source: apps/api/services/tax_service.py) - TASK-0049 - When completed: _
- [ ] Remove stale tax rules that no longer appear in provider syncs (Source: apps/api/services/tax_service.py) - TASK-0050 - When completed: _
- [ ] Issue refresh tokens with rotation for long-lived sessions (Source: apps/api/security.py & apps/api/routers/auth.py) - TASK-0051 - When completed: _
- [ ] Cache organisation membership lookups for high-traffic permission checks (Source: apps/api/security.py) - TASK-0052 - When completed: _
- [ ] Implement retry and backoff for transient scheduler database connectivity issues (Source: apps/api/scheduler.py) - TASK-0053 - When completed: _
- [ ] Emit metrics or alerts when scheduler refresh cadence falls behind schedule (Source: apps/api/scheduler.py) - TASK-0054 - When completed: _
- [ ] Externalise scheduler refresh cadence into per-organisation configuration (Source: apps/api/scheduler.py) - TASK-0055 - When completed: _
- [ ] Revisit audit log context reset handling for cross-thread usage (Source: apps/api/audit.py) - TASK-0056 - When completed: _
- [ ] Support asynchronous audit log flushing to reduce hot path latency (Source: apps/api/audit.py) - TASK-0057 - When completed: _
- [ ] Load the provider catalog from persistence so admin edits survive restarts (Source: apps/api/config.py) - TASK-0058 - When completed: _
- [ ] Replace runtime `create_all` calls with Alembic-managed migrations (Source: apps/api/db.py & REPORTS/001_DIAGNOSIS.md) - TASK-0059 - When completed: _
- [ ] Swap eager schema creation for idempotent migration bootstrapping (Source: apps/api/db.py) - TASK-0060 - When completed: _
- [x] Incorporate database and scheduler checks into the health response payload (Source: apps/api/routers/core.py) - TASK-0061 - When completed: 2025-10-30, [REPORT-2025-10-30-1](REPORTS.md#report-2025-10-30-1)
- [ ] Cache provider metadata and expose version compatibility information in health endpoints (Source: apps/api/routers/core.py) - TASK-0062 - When completed: _
- [ ] Add pagination controls to workflow router staging table endpoints (Source: apps/api/routers/workflow.py) - TASK-0063 - When completed: _
- [ ] Cache report refresh results to avoid repeated model executions (Source: apps/api/routers/reports.py) - TASK-0064 - When completed: _
- [ ] Stream large forecast CSV exports to mitigate memory pressure (Source: apps/api/routers/reports.py) - TASK-0065 - When completed: _
- [ ] Reuse a per-request service cache in ledger router handlers to avoid redundant instantiations (Source: apps/api/routers/ledger.py) - TASK-0066 - When completed: _
- [ ] Validate account code uniqueness prior to delegating to ledger services (Source: apps/api/routers/ledger.py) - TASK-0067 - When completed: _
- [ ] Capture posting source metadata for reconciliation dashboards (Source: apps/api/routers/ledger.py) - TASK-0068 - When completed: _
- [ ] Support comparative periods and currency filters in trial balance responses (Source: apps/api/routers/ledger.py) - TASK-0069 - When completed: _
- [ ] Add cursor-based pagination to audit router endpoints (Source: apps/api/routers/audit.py) - TASK-0070 - When completed: _
- [ ] Pool forecast service instances to reuse expensive model state (Source: apps/api/routers/forecast.py) - TASK-0071 - When completed: _
- [ ] Validate forecast series length against the requested horizon (Source: apps/api/routers/forecast.py) - TASK-0072 - When completed: _
- [ ] Emit structured metrics for malformed identifier headers (Source: apps/api/dependencies.py) - TASK-0073 - When completed: _
- [ ] Validate header provenance to prevent spoofed audit metadata (Source: apps/api/dependencies.py) - TASK-0074 - When completed: _
- [ ] Bind actor context to authentication session identifiers for replay protection (Source: apps/api/dependencies.py) - TASK-0075 - When completed: _
- [ ] Dispatch background FX sync jobs for longer historical windows (Source: apps/api/routers/fx.py) - TASK-0076 - When completed: _
- [ ] Capture FX provider latency metrics to tune retry policies (Source: apps/api/routers/fx.py) - TASK-0077 - When completed: _
- [ ] Implement rate limiting for authentication flows alongside refresh tokens (Source: REPORTS/001_DIAGNOSIS.md) - TASK-0078 - When completed: _
- [ ] Enforce organisation scoping and pagination safeguards across reports and workflow routers (Source: REPORTS/001_DIAGNOSIS.md) - TASK-0079 - When completed: _
- [ ] Enhance plugin loader validation, cache invalidation, and health checks (Source: REPORTS/001_DIAGNOSIS.md) - TASK-0080 - When completed: _
- [ ] Expand strict typing coverage to the remaining services and routers (Source: REPORTS/001_DIAGNOSIS.md) - TASK-0081 - When completed: _
- [ ] Broaden observability metrics instrumentation per stewardship notes (Source: REPORTS/001_DIAGNOSIS.md) - TASK-0082 - When completed: _
- [ ] Add structured failure logging hooks during API startup (Source: REPORTS/003_CODEX_STEP1.md) - TASK-0083 - When completed: _
- [ ] Automate plugin cache invalidation when provider configuration changes (Source: REPORTS/003_CODEX_STEP1.md) - TASK-0084 - When completed: _
- [ ] Implement multi-factor authentication support for secure sign-ins (Source: REPORTS/001_DIAGNOSIS.md) - TASK-0085 - When completed: _

---
