# Release Notes

## Highlights
- Rebuilt the `macli` CLI diagnostics commands with deterministic table/JSON
  output, added regression tests for health/observability snapshots, and made
  the scheduler tolerant of missing legacy models so automation entry points
  keep working while the database layer is modernised.
- Hardened API startup orchestration with abort summaries for fatal failures,
  skip telemetry, and extended regression coverage while restoring Makefile
  tab alignment so `make health`/`make quality-gate` operate correctly in CI.
- Added health-check telemetry metrics, an observability snapshot API consumed
  by the new `macli observe` command, the `ops:resilience` incident playbook
  extension, optional observability contract scaffolding via
  `macli scaffold-extension --observability-contract`, and a scripted
  `make quality-gate` target for consolidated lint/type/test/security runs.
- Hardened scenario plan parsing by reinstating union-aware validation, adding
  byte-string tag normalisation, and extending loader regression tests to catch
  invalid defaults before orchestration reaches provider adapters.
- Promoted scenario plans to first-class application artifacts, shipping
  `ScenarioPlan`/`ScenarioPlanSummary`, a `macli inspect-plan` CLI command, the
  `/snapshot/plans/preview` API route, Streamlit plan previews, and refreshed
  docs so agents can validate coverage before running provider workloads.
- Added async-aware scenario telemetry instrumentation with matching pytest
  coverage, removed cache observer import cycles so adapters can be tested in
  isolation, and fixed Makefile tabs to keep `make ci` usable in automation.
- Instrumented scenario batches with dedicated metrics/tracing, exposed
  extension contracts through `macli inspect-contracts` and the new
  `/extensions/contracts` API, shipped the `scenarios:variance` reference
  extension, and introduced `make release`/`tools.release_manager` to automate
  version bumps alongside changelog and release note updates.
- Normalised timezone helpers and modernised collections usage in the
  observability/domain layers, collapsed deprecated snapshot/telemetry shims
  onto the application equivalents, refreshed scenario orchestration utilities
  plus CLI/tests, and lifted the lint/format line length budget to 120
  characters to avoid spurious violations.
- Simplified ledger CSV ingestion by modularising validation helpers, taught
  the audit metrics CLI to reuse cached trace coverage, refreshed stewardship
  metrics, and documented telemetry sentinel automation roles for long-term
  monitoring.
- Instrumented extension loading with Prometheus counters/gauges, exposed a
  `/health/telemetry` rollup endpoint, introduced `macli inspect-extensions`,
  and shipped the `ops:heartbeat` reference extension plus refreshed
  architecture/automation guides for long-term observability stewardship.
- Hardened audit provenance helpers to default to UTC timestamps, tightened
  tracing exporter fallbacks to avoid lambda sentinels, and smoothed Streamlit
  snapshot tooling so observability remains predictable even without optional
  dependencies.
- Introduced lightweight tracing with HTTP middleware, CLI span helpers, and a
  tracing health probe so operators can follow requests end-to-end. Added an
  optional cashflow analytics reference extension and the `macli scaffold-extension`
  command for rapid module generation.
- Hardened the snapshot telemetry provider to log missing observability modules
  and surface unexpected import failures during startup, backed by new
  regression tests.
- Introduced a provider-backed snapshot orchestrator powering the `/snapshot`
  API route and the `macli snapshot` CLI command, returning provider
  provenance, cache metrics, and consolidated FX/commodity/tax data.
- Introduced Prometheus-compatible metrics, request instrumentation middleware,
  and health endpoints under `/health/*` for observability.
- Added an extension registry (`apps/extensions/`) with a baseline analytics
  extension plus CLI commands (`macli health`, `macli extensions`) to manage
  operational state.
- Shipped `tools.audit_metrics` with a `make audit` wrapper so coverage,
  complexity, and dependency ratios can be regenerated without `pytest-cov`.
- Published new collateral (`ARCHITECTURE_OVERVIEW.md`, `EXTENSION_GUIDE.md`,
  `AUTOMATION.md`) and a Makefile-driven quality pipeline to simplify future
  contributions.

## Upgrade Guidance
- Optionally install `opentelemetry-sdk` and `opentelemetry-exporter-otlp` when
  deploying to stream traces to external collectors; without these packages the
  tracer falls back to console logging.
- Ensure any custom `apps.observability.metrics` modules import cleanly; the
  telemetry provider now raises unexpected runtime errors instead of silently
  disabling instrumentation so issues can be remediated promptly.
- No breaking changes. The API gains `/health` routes and metrics without
  impacting existing routers.
- Optional: install `prometheus-client` when deploying to ensure metrics export
  works; `make install` already handles this locally.
- Update automation to call `make quality` and `make health` instead of ad-hoc
  lint/test scripts, and include `make audit` when compiling steward reports.
- Incorporate `make quality-gate` and `macli observe` into operational runbooks
  to capture an aggregated telemetry snapshot alongside the existing health
  probes. Enable the `ops:resilience` extension (default in configuration) to
  expose the incident playbook contract to agents.
- When re-running audits in constrained environments, prefer
  `python -m tools.audit_metrics --skip-trace` to reuse the prior coverage
  snapshot while still emitting complexity and dependency metrics.
- Add `python -m cli.macli inspect-extensions` to operational checklists to
  confirm extension manifests load and surface version metadata during releases.

## Known Issues / Follow Ups
- Legacy TODOs still require priority/effort tags; future cleanup will align
  the remaining backlog with the new convention.
- OTLP export is optional; install the OpenTelemetry extras noted above to ship
  traces to a collector.
