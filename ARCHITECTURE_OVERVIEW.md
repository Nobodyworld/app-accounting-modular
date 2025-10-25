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
│    services/telemetry.py)      │   └───────────┬────────────────────────┘
└───────────────┬───────────────┘               │
                │                                │
┌───────────────▼───────────────┐   ┌───────────▼────────────────────────┐
│ Domain Ports & Providers       │   │ Extension Registry                 │
│ - Ports (apps/modular_         │   │ - apps/extensions/registry.py      │
│   accounting/domain/ports.py)  │   │ - Default extension loader         │
│ - Provider loader (apps/api/   │   │   (apps/api/services/               │
│   services/plugin_loader.py)   │   │    extension_loader.py)             │
│ - Built-in plugins (plugins/)  │   │ - Baseline analytics extension     │
└───────────────────────────────┘   │   (plugins/analytics_baseline/)      │
                                     └────────────────────────────────────┘
```

## Runtime flow

1. **Entry points** initialise logging, metrics middleware, and database state.
   The FastAPI app adds `RequestMetricsMiddleware` so every request is counted
   and timed, while the CLI uses `logging_context` to provide correlation IDs.
2. **Extension loader** imports every enabled module declared in
   `Settings.allowed_extensions`. Extensions register an `ExtensionManifest`
   with `apps.extensions.registry.extension_registry` and can contribute health
   checks or custom instrumentation.
3. **Application services** orchestrate domain operations. For example,
   `DataSnapshotService` normalises `SnapshotRequest` payloads, resolves data
   through ports, and now records cache utilisation and latency metrics via the
   telemetry adapter.
4. **Domain ports and providers** continue to act as the integration boundary
   for external data. Providers are loaded via the existing plugin loader and
   the new extension registry complements rather than replaces this system.
5. **Observability** collects metrics and health reports. Metrics are exposed
   through `/health/metrics` and health probes through `/health/live` and
   `/health/ready`. Extensions can register additional probes without touching
   API code.

## Operational safeguards

* Health probes cover database connectivity, scheduler state, metrics export,
  and registered extensions. CLI tooling mirrors these checks via
  `macli health`.
* The `Makefile` standardises quality gates: linting, type checks, tests with
  a coverage threshold, and optional safety scans.
* Cache observers feed Prometheus-compatible counters and gauges so cache hit
  rates and entry counts can be monitored over time.

## Extension lifecycle

1. Declare an extension module in configuration (defaults ship with
   `observability:demo`).
2. Implement a `register(registry)` function that publishes a manifest and
   registers optional hooks.
3. The loader imports the module on application startup, populating manifests
   and exposing metadata to the CLI (`macli extensions`) and HTTP API.

This design allows new feature packs—report exporters, automation bridges, or
AI agents—to be bolted on by registering extensions instead of modifying core
packages.
