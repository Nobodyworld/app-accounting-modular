# Extension Development Guide

This guide walks through creating a Modular Accounting extension that plugs
into the new registry, publishes metadata, and contributes observability hooks.

## Anatomy of an extension

Extensions live in importable Python modules. Each module should expose a
`register(registry: ExtensionRegistry)` function and optionally a module-level
`MANIFEST` describing the extension. The quickest way to bootstrap a new
package is the `macli scaffold-extension` command which generates the skeleton
files described below, complete with tracing hooks and a health probe. Pass
`--observability-contract` to scaffold a starter incident playbook contract that
matches the pattern used by the `ops:resilience` reference extension.

```python
from apps.extensions import ExtensionManifest, ExtensionRegistry

MANIFEST = ExtensionManifest(
    key="acme:automations",
    name="ACME Automations",
    version="0.1.0",
    description="Adds background automations for ACME workflows",
    capabilities=("automation", "webhooks"),
    author="ACME Corp",
)


def register(registry: ExtensionRegistry) -> None:
    registry.register(MANIFEST)
    registry.register_health_check(MANIFEST.key, _health_check)


def _health_check() -> bool:
    return True  # Replace with meaningful diagnostics
```

When `register` executes it can:

* Publish health checks via `registry.register_health_check`.
* Interact with observability helpers (for example, expose new metrics).
* Import and configure background jobs or routers as required.

The `apps.observability.metrics.ExtensionTelemetryAdapter` automatically tracks
load success and latency for every enabled module. Extensions can build on top
of this by registering their own metrics—see the `plugins/ops_heartbeat`
package for a reference that publishes a heartbeat gauge alongside its health
probe.

## Wiring extensions into configuration

Extensions are configured through `Settings.allowed_extensions`. The default
configuration (see `apps/api/config.py`) already enables the baseline
observability extension shipped in `plugins/analytics_baseline`.

To enable your own module add an entry to your environment variables or a
settings override file:

```
MODACCT_ALLOWED_EXTENSIONS__acme:automations__module=acme.extensions.automations
MODACCT_ALLOWED_EXTENSIONS__acme:automations__enabled=true
```

Once configured the loader will import the module at startup. You can verify
installation via:

* `GET /health/ready` – the response will include health reports contributed by
  extensions.
* `GET /health/telemetry` – aggregates metrics, health probes, and extension
  load status for dashboards or automation.
* `GET /health/metrics` – metrics registered by extensions appear in the
  Prometheus exposition.
* `macli inspect-extensions` – the CLI lists configured extensions, manifest
  metadata, and whether they loaded successfully. `--format json` produces a
  machine-friendly snapshot for automation.
* `macli scaffold-extension reporting:example --observability-contract` –
  generates a ready-to-edit package in `plugins/` with a health probe and an
  incident playbook contract.
* `macli observe` – emits an aggregated telemetry snapshot (metrics, health,
  tracing) that includes extension readiness and contract exposure.

## Testing extensions

* Unit tests can instantiate `ExtensionRegistry` directly and invoke your
  `register` function to assert manifest and hook behaviour.
* Integration tests should import your module and ensure the loader surfaces it
  correctly. See `tests/test_extension_loader.py` for examples.
* Health checks should be deterministic and fast. Prefer pure functions or
  guarded network calls with tight timeouts.

## Advertising automation contracts

Extensions can publish structured contracts so downstream agents know which
automation hooks exist. Register contracts with the new
`ExtensionContract` dataclass; see `plugins/ops_resilience` for a full example
that exposes an incident playbook contract consumed by operators.

```python
from apps.extensions import ExtensionContract

VARIANCE_CONTRACT = ExtensionContract(
    kind="scenario-augmentation",
    name="Base currency variance",
    version="1.0.0",
    entrypoint="plugins.my_extension.variance:generate_variants",
    description="Generates +/-5% stress variants for snapshot scenarios.",
    tags=("stress", "fx"),
)


def register(registry: ExtensionRegistry) -> None:
    registry.register(MANIFEST)
    registry.register_contract(MANIFEST.key, VARIANCE_CONTRACT)
```

The CLI exposes registered contracts via `python -m cli.macli inspect-contracts`
while the API serves them at `GET /extensions/contracts`. Both surfaces include
extension metadata, enabling orchestration pipelines to auto-discover new
capabilities without bespoke glue code.

## Publishing best practices

* Keep extension keys namespaced (`vendor:feature`) to avoid collisions.
* Document capabilities in the manifest—this metadata powers dashboards and
  automation.
* Use the Makefile quality targets (`make quality`) before publishing to ensure
  linting, typing, and coverage gates pass consistently.
* Refer to `plugins/ops_heartbeat` and `plugins/ops_resilience` when wiring
  observability for operational add-ons; they demonstrate registering gauges,
  emitting heartbeat probes, publishing contracts, and integrating with the
  extension registry without touching core modules.
