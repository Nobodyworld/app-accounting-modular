# Provider SDK Architecture

## Status

The v0.5 provider SDK is the installable `modular-accounting-provider-sdk` distribution. Its authoritative import is `modular_accounting_provider_sdk`; `apps.provider_sdk` is a thin compatibility facade over the same objects. It remains part of the modular accounting-control toolkit, not a provider marketplace, package manager, tenant authorization system, or production certification program.

The repository remains an **Early Beta / Portfolio Preview** with a local-demonstration deployment boundary.

## Design goals

The SDK must let provider authors and application owners answer five questions deterministically:

1. What provider key, implementation version, capabilities, network policy, credential-variable names, and data classification does the module declare?
2. Does the module match the public SDK and the application API major?
3. Does the configured allowlist entry match the manifest?
4. Does the synchronous factory and provider type expose the required structural interface?
5. Can the application instantiate the provider only after every authorization and conformance check passes?

The SDK must answer those questions without tenant data, application sessions, database sessions, credentials, or provider data/network calls.

## Trust boundaries

```text
Importable Python module
        |
        | does not imply authorization
        v
Application provider allowlist
        |
        | exact key + module + configured capabilities
        v
Structural conformance
        |
        | manifest / SDK / API / factory / provider shape
        v
Runtime provider construction
        |
        | only after all required checks pass
        v
Accounting application service
        |
        | tenant scope / limits / provenance / audit / persistence
        v
Accountant-facing result
```

### Boundary 1 — importability

A Python module being importable is not sufficient for application use. There is no arbitrary package scan, filesystem scan, entry-point scan, or manifest-driven auto-enablement.

### Boundary 2 — allowlist authorization

`settings.allowed_providers` remains the installation and authorization boundary. It supplies the configured provider key, module path, display metadata, and capabilities. Application callers load by configured key, not by arbitrary module path.

### Boundary 3 — structural conformance

The conformance engine validates:

- module import;
- `PROVIDER_MANIFEST` type and bounded metadata;
- provider SDK version;
- application API-major compatibility;
- configured key and capability equality;
- optional module/manifest version equality;
- configured factory name;
- synchronous callable factory with no required arguments;
- provider name; and
- capability-specific method and parameter names.

Structural conformance does not call provider data/network methods. When a factory return annotation resolves to an inspectable type, the engine creates an uninitialized structural instance with `object.__new__` and inspects bound method signatures. It does not execute the provider constructor.

When the return type cannot be inspected safely, the report emits a bounded warning and defers instance-level checks to runtime loading.

### Boundary 4 — runtime construction

`load_conforming_provider` repeats the required checks, invokes the synchronous factory, rejects `None` and awaitables, validates the returned provider name and signatures, and returns the instance with its manifest and conformance report.

Import and factory exceptions are sanitized to stable action and exception-class evidence. Arbitrary exception text, credentials, provider response bodies, and local paths are not emitted.

### Boundary 5 — application services

The SDK does not make accounting decisions. Existing services remain authoritative for:

- tenant and organization scope;
- authorization order;
- request, record, byte, date-range, timeout, and retry limits;
- data normalization and validation;
- provenance and freshness;
- Decimal-safe accounting behavior;
- persistence and transactionality;
- audit identity and events; and
- accountant-facing results and exports.

Provider code must not bypass these services.

## Public types

The public `apps.provider_sdk` package exports:

- `ProviderManifest` and bounded manifest constants;
- capability protocols for bank, FX, macro, market, and tax providers;
- capability-to-method and capability-to-parameter maps;
- deterministic conformance check/report types;
- structural inspection and runtime loading functions; and
- deterministic scaffolding helpers.

The package intentionally has no tenant, database, web, scheduler, or provider-network dependency.

## Manifest model

`ProviderManifest` is a frozen, slotted dataclass. Construction normalizes optional text and sorted tuples, rejects duplicate or unknown capabilities, validates semantic/API/SDK version shapes, restricts public metadata lengths, enforces HTTPS homepages, and accepts only uppercase credential environment-variable names.

The manifest serializes to stable JSON-compatible primitives. Credential values are never part of the model.

Current key grammar preserves established allowlist identifiers such as `market:commodities_demo` and `tax:oecd_vat` while still requiring a lowercase namespaced key.

## Capability contracts

| Capability | Required provider interface |
| --- | --- |
| `fx` | `sync_daily_rates(base, date_)` |
| `market` | `fetch_prices(symbol, start, end)` |
| `tax` | `upsert_rules()` |
| `macro` | `fetch_series(series_id, start, end)` |
| `bank` | `list_accounts()` and `fetch_transactions(account_id, start, end)` |

The SDK checks parameter names and rejects missing methods or additional required parameters. Return-value semantics remain provider/service specific and require provider-focused tests.

## Descriptor integration

`provider_descriptors()` performs cached structural inspection for configured providers and exposes:

- existing public provider metadata;
- module and implementation version;
- API/provider compatibility;
- manifest metadata; and
- the full deterministic conformance report.

Descriptor inspection does not invoke factories. Cache signatures include key, module, display name, description, and capabilities so configuration changes invalidate the descriptor view. `refresh_provider_cache()` explicitly clears metadata and conformance caches.

A nonconforming descriptor is marked `incompatible` with stable failure codes. Health and `/providers` surfaces can present that evidence without exposing provider exception text.

## CLI integration

The `provider-sdk` command group provides:

- `validate --key <configured-key>`;
- `validate --module <import-module>` for authoring inspection only;
- `validate --all-configured`;
- table or sorted JSON evidence;
- structural-only or explicit factory-instantiation modes; and
- deterministic provider scaffolding.

Module validation does not authorize application use. Only an allowlist entry enables runtime loading by configured key.

## Scaffold architecture

The scaffold generator creates a bounded package under an operator-selected directory:

- `__init__.py`;
- `provider.py` with manifest, typed factory, and capability-shaped starter methods;
- `README.md`; and
- `tests/test_conformance.py`.

Generation is deterministic and LF-normalized. Evidence paths are relative to the requested directory. Without `force`, any known generated file blocks replacement. With `force`, only known generated files are overwritten; unrelated owner files remain.

Generated provider methods are non-networked placeholders returning empty collections. Provider authors must add bounded adapter logic and provider-specific tests before allowlist integration.

## Failure model

Required checks fail closed. Reports contain bounded check codes, statuses, and messages. Warnings do not fail a report; any `fail` check does.

Stable failure codes are suitable for CI, health, and review evidence. They are not intended to carry arbitrary exception strings or raw external data.

## Test architecture

Required tests cover:

- valid, invalid, duplicate, unknown, and bounded manifest fields;
- all capability method signatures;
- key/capability/version drift;
- missing, asynchronous, raising, `None`, and awaitable factories;
- missing provider names and methods;
- sanitized import and factory failures;
- deterministic JSON and table evidence;
- scaffold path safety, overwrite behavior, LF output, determinism, and generated-package conformance;
- allowlist-first runtime loading;
- descriptor caching and invalidation;
- all configured bundled-provider manifests and policies; and
- patched network entry points proving structural checks remain non-networked.

The SDK, conformance, scaffold, CLI, and loader modules are enrolled in targeted mypy and explicit critical line/branch coverage policy. Aggregate coverage may not hide regressions in these modules.

## Versioning

The provider SDK version is independent from provider implementation versions. A provider declares:

- SDK major/minor compatibility, currently `1.0`;
- application API major compatibility, currently `0`; and
- its own semantic implementation version.

The application may evolve provider SDK and API compatibility independently. A future compatibility policy may support bounded version ranges, deprecations, signatures, or attestations. Those changes require explicit design and evidence; the current contract uses exact SDK version and API-major equality.

## Deliberate non-goals

This architecture does not provide:

- marketplace publication or search;
- automatic package installation or enablement;
- code execution from user uploads;
- credential storage or brokerage;
- tenant authorization through manifests;
- provider-data accuracy certification;
- signed distribution, trust tiers, revocation, or vulnerability response for third parties;
- public-hosting approval; or
- production accounting, tax, treasury, market-data, or bank-feed certification.

See [`../guides/provider_sdk.md`](../guides/provider_sdk.md) for authoring, [`../provider-compatibility.md`](../provider-compatibility.md) for the bundled matrix, and [`../PLUGINS.md`](../PLUGINS.md) for the provider/extension distinction.
