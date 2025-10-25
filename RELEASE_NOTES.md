# Release Notes

## Highlights
- Introduced Prometheus-compatible metrics, request instrumentation middleware,
  and health endpoints under `/health/*` for observability.
- Added an extension registry (`apps/extensions/`) with a baseline analytics
  extension plus CLI commands (`macli health`, `macli extensions`) to manage
  operational state.
- Published new collateral (`ARCHITECTURE_OVERVIEW.md`, `EXTENSION_GUIDE.md`,
  `AUTOMATION.md`) and a Makefile-driven quality pipeline to simplify future
  contributions.

## Upgrade Guidance
- No breaking changes. The API gains `/health` routes and metrics without
  impacting existing routers.
- Optional: install `prometheus-client` when deploying to ensure metrics export
  works; `make install` already handles this locally.
- Update automation to call `make quality` and `make health` instead of ad-hoc
  lint/test scripts.

## Known Issues / Follow Ups
- Legacy TODOs still require priority/effort tags; future cleanup will align
  the remaining backlog with the new convention.
- Full OpenTelemetry tracing remains on the roadmap (see `apps/observability/__init__.py`).
