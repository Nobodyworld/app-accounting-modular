# Operations & Incident Response

The Modular Accounting platform now exposes cohesive observability primitives
so incidents can be triaged rapidly.

## Health Probes

- `/health/live` – liveness check.
- `/health/ready` – readiness check returning per-subsystem status (database,
  scheduler, metrics, tracing, and extension contributions).
- `/health/metrics` – Prometheus exposition including HTTP and cache metrics.

Run `make health` or `macli health` for a CLI snapshot of the same probes.

## Tracing

- Tracing is configured via `apps.observability.tracing.configure_tracing`.
- FastAPI mounts `RequestTraceMiddleware` which accepts incoming `traceparent`
  headers and sets a new one on responses.
- CLI commands wrap work units in `traced` so logs include `trace_id` and
  `span_id` fields.
- Health checks expose tracing exporter configuration under the `tracing` probe.

When OpenTelemetry libraries are installed, the tracer automatically exports
spans via console or OTLP exporters. Without them, spans are logged locally.

## Incident Response Flow

1. Capture health: `make health` and `/health/ready` for live snapshots.
2. Gather traces: use the `trace_id` emitted in CLI/HTTP logs to follow the
   request path across services.
3. Review metrics: scrape `/health/metrics` to inspect request rates, latencies,
   cache utilisation, and extension counters.
4. Decide on remediation: disable suspect extensions via configuration or roll
   back to a known good commit. The `macli extensions` command lists active
   modules.
5. Document the outcome in `STEWARDS_REPORT.md` so future operators understand
   the action taken.

## Developer Tooling

- `make ci` – run linting, typing, tests (coverage ≥ 85%), and security scans.
- `macli scaffold-extension` – generate extension scaffolding with tracing and
  health hooks.
- `tools/release.py` (see CONTRIBUTING) – helper for preparing release notes and
  changelog entries.
