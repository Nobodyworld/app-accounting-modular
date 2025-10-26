# Architecture Overview

Modular Accounting now exposes a layered architecture with shared observability
and extension scaffolding so that new modules can be introduced without
touching the core. The diagram below illustrates the major runtime surfaces.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                             Entry Points                                 │
│  - FastAPI (apps/api/main.py)                                            │
│  - CLI (cli/macli.py)                                                    │
│  - Scheduled jobs (apps/api/scheduler.py)                                │
└───────────────┬───────────────────────────────┬──────────────────────────┘
                │                               │
┌───────────────▼───────────────┐   ┌───────────▼────────────────────────┐
│ Application Services           │   │ Observability Layer                 │
│ - DataSnapshotService          │   │ - Structured logging                │
│   (apps/modular_accounting/    │   │   (apps/observability/logging.py)   │
│    application/snapshots.py)   │   │ - Metrics + health registry         │
│ - Telemetry adapter            │   │   (apps/observability/{metrics,     │
│   (apps/modular_accounting/    │   │    health}.py)                      │
│    application/telemetry.py)   │   │ - ExtensionTelemetryAdapter         │
│ - Tracing context helpers      │   │   (apps/observability/metrics.py)   │
│   (apps/observability/tracing.py)│ │ - Tracing + trace middleware        │
└───────────────┬───────────────┘   │   (apps/observability/tracing.py)   │
                │                   └───────────┬────────────────────────┘
                │                                │
┌───────────────▼───────────────┐   ┌───────────▼────────────────────────┐
│ Domain Ports & Providers       │   │ Extension Registry                 │
│ - Ports (apps/modular_         │   │ - apps/extensions/registry.py      │
│   accounting/domain/ports.py)  │   │ - Default extension loader         │
│ - Provider loader (apps/api/   │   │   (apps/api/services/               │
│   services/plugin_loader.py)   │   │    extension_loader.py)             │
│ - Built-in plugins (plugins/)  │   │ - Baseline analytics extension     │
└───────────────────────────────┘   │   (plugins/analytics_baseline/)      │
                                     │ - Operations heartbeat extension    │
                                     │   (plugins/ops_heartbeat/)          │
                                     └────────────────────────────────────┘
```

## Runtime flow

1. **Entry points** initialise logging, tracing, metrics middleware, and
   database state. The FastAPI app wires both `RequestTraceMiddleware` and
   `RequestMetricsMiddleware` so every request gains a traceparent header and
   latency metrics, while the CLI uses `logging_context` + `traced` to provide
   correlation IDs and trace IDs for background work.
2. **Extension loader** imports every enabled module declared in
   `Settings.allowed_extensions`. Extensions register an `ExtensionManifest`
   with `apps.extensions.registry.extension_registry` and can contribute health
   checks or custom instrumentation. The loader now emits metrics via
   `ExtensionTelemetryAdapter` so dashboards can monitor load durations and
   gauge whether a module is both enabled and successfully initialised.
3. **Application services** orchestrate domain operations. For example,
   `DataSnapshotService` normalises `SnapshotRequest` payloads, resolves data
   through ports, and records cache utilisation and latency metrics via the
   telemetry adapter. `ScenarioSnapshotRunner` layers on top of the snapshot
   service to execute multiple `SnapshotScenario` definitions, aggregate
   diagnostics, and expose the batch to both the CLI and HTTP endpoint without
   duplicating orchestration logic. Scenario executions emit dedicated metrics
   (`modacct_scenario_runs_total`, `modacct_scenario_latency_seconds`, and
   `modacct_scenario_inflight`) so dashboards can correlate orchestration load
   with cache performance. `compute_snapshot_diagnostics` converts the
   immutable snapshot into freshness and coverage metrics so every surface can
   surface a consistent health summary without reimplementing the analysis.
4. **Domain ports and providers** continue to act as the integration boundary
   for external data. Providers are loaded via the existing plugin loader and
   the new extension registry complements rather than replaces this system.
5. **Observability** collects metrics, traces, and health reports. Metrics are
   exposed through `/health/metrics` while `/health/telemetry` aggregates the
   current Prometheus exposition, registered health probes, and extension load
   status. Health probes cover database connectivity, scheduler state, tracing
   exporter configuration, and extension readiness. Extensions can register
   additional probes without touching API code. The tracing module ships a
   `_noop_exporter` sentinel so spans cleanly downgrade to console logging when
   OpenTelemetry exporters are unavailable. `/extensions/contracts` and the
   companion `macli inspect-contracts` command extend observability to the
   automation plane by surfacing which contracts are currently published.

## Operational safeguards

* Health probes cover database connectivity, scheduler state, metrics export,
  tracing configuration, and extension readiness. CLI tooling mirrors these
  checks via `macli health`, `macli inspect-extensions`, and
  `macli inspect-contracts` so automation has a consistent view of manifests and
  published contracts.
* The `Makefile` standardises quality gates: linting, type checks, tests with a
  coverage threshold, optional safety scans, and the `audit` target for
  trace-based coverage + complexity metrics.
* Cache observers feed Prometheus-compatible counters and gauges so cache hit
  rates and entry counts can be monitored over time, while
  `ExtensionTelemetryAdapter` tracks load latency and success counts.

## Extension lifecycle

1. Declare an extension module in configuration (defaults ship with
   `observability:demo` and the disabled `reporting:cashflow` reference).
2. Implement a `register(registry)` function that publishes a manifest and
   registers optional hooks.
3. The loader imports the module on application startup, populating manifests,
   registering optional contracts, and exposing metadata to the CLI (`macli
   inspect-extensions`, `macli inspect-contracts`) and HTTP API.

This design allows new feature packs—report exporters, automation bridges, or
AI agents—to be bolted on by registering extensions instead of modifying core
packages. The `macli scaffold-extension` command now generates a fully wired
package skeleton with tracing hooks so contributors can start from a proven
baseline. `macli inspect-extensions` provides an immediate, metrics-backed
snapshot of enabled modules, and the `plugins/ops_heartbeat` extension serves as
a reference for emitting extension-specific telemetry.

## Future-proofing

* **Containerisation** – The API is stateless and depends only on the database;
  deploy behind a load balancer with per-instance caches disabled when scaling
  horizontally. Health endpoints (`/health/live`, `/health/ready`, and
  `/health/telemetry`) are safe for Kubernetes probes.
* **Multi-tenant support** – Persist extension configuration in a tenant-aware
  store and use the extension loader as the boundary for injecting tenant
  context. The telemetry adapters already label metrics by module path, making
  it straightforward to add tenant labels in the future.
* **Automation hooks** – Extension manifests surface capabilities so automation
  agents can decide which module to invoke, while explicit contracts document
  the callable surfaces available to agents. Coupled with the incident response
  guidelines in `AUTOMATION.md`, this enables future agentic tooling to safely
  orchestrate new connectors.
* **Release automation** – `tools.release_manager` underpins `make release`,
  which bumps semantic versions and seeds changelog/release notes to keep
  provenance tight as the platform evolves.
