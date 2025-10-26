# Release Notes

## Highlights
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

## Known Issues / Follow Ups
- Legacy TODOs still require priority/effort tags; future cleanup will align
  the remaining backlog with the new convention.
- OTLP export is optional; install the OpenTelemetry extras noted above to ship
  traces to a collector.
