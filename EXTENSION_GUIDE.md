# Extension Development Guide

This guide walks through creating a Modular Accounting extension that plugs
into the new registry, publishes metadata, and contributes observability hooks.

## Anatomy of an extension

Extensions live in importable Python modules. Each module should expose a
`register(registry: ExtensionRegistry)` function and optionally a module-level
`MANIFEST` describing the extension. The quickest way to bootstrap a new
package is the `macli scaffold-extension` command which generates the skeleton
files described below, complete with tracing hooks and a health probe.

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
* `GET /health/metrics` – metrics registered by extensions appear in the
  Prometheus exposition.
* `macli extensions` – the CLI lists configured extensions and whether they
  loaded successfully.
* `macli scaffold-extension reporting:example` – generates a ready-to-edit
  package in `plugins/` to accelerate development. The scaffolder mirrors the
  reference `reporting:cashflow` extension that now ships disabled by default.

## Testing extensions

* Unit tests can instantiate `ExtensionRegistry` directly and invoke your
  `register` function to assert manifest and hook behaviour.
* Integration tests should import your module and ensure the loader surfaces it
  correctly. See `tests/test_extension_loader.py` for examples.
* Health checks should be deterministic and fast. Prefer pure functions or
  guarded network calls with tight timeouts.

## Publishing best practices

* Keep extension keys namespaced (`vendor:feature`) to avoid collisions.
* Document capabilities in the manifest—this metadata powers dashboards and
  automation.
* Use the Makefile quality targets (`make quality`) before publishing to ensure
  linting, typing, and coverage gates pass consistently.
