# Provider SDK and Conformance Guide

The Modular Accounting provider SDK is a dependency-light authoring and review boundary for accounting-data adapters. It lets a provider author describe an adapter, implement one or more supported capability shapes, generate deterministic structural evidence, and request explicit inclusion in the application allowlist.

The SDK does **not** install packages, discover arbitrary code, grant tenant access, store credentials, call provider data methods during structural validation, or certify an adapter for production use. The repository remains an **Early Beta / Portfolio Preview** with a local-demonstration deployment boundary.

## Trust model

A provider participates in three separate decisions:

1. **Package declaration** — the provider module exports a bounded `PROVIDER_MANIFEST` and a synchronous factory.
2. **Structural conformance** — the SDK checks metadata, compatibility, factory shape, provider name, required methods, and required parameter names without invoking provider data methods.
3. **Application authorization** — `settings.allowed_providers` explicitly maps an approved provider key to an import module and configured capabilities.

A manifest is descriptive. It cannot add itself to the allowlist, authorize a tenant, obtain a database session, access an authenticated application session, or override network/request limits.

## From operator trust to organization policy

The v0.4 governance layer keeps process trust and tenant policy separate:

1. an operator places a reviewed key/module/capability tuple in `settings.allowed_providers`;
2. `provider-sdk governance-reconcile` runs structural conformance and persists only safe identity evidence;
3. an organization administrator may enable/disable that already-trusted key and select a revision-protected capability default; and
4. runtime resolution intersects current process trust, registration identity, conformance/compatibility, capability, and organization policy before constructing the provider.

Use `provider-sdk governance-validate` to report current drift and `provider-sdk governance-export --organization-id ID` for deterministic secret-free evidence. Reconciliation does not call provider data methods or access a remote registry. Historical or tenant-provided persistence can never provide an import path. This workflow is governance for an operator-trusted catalog, not a marketplace or certification process.

## Supported capability contracts

| Capability | Required methods | Required parameter names |
| --- | --- | --- |
| `fx` | `sync_daily_rates` | `base`, `date_` |
| `market` | `fetch_prices` | `symbol`, `start`, `end` |
| `tax` | `upsert_rules` | none |
| `macro` | `fetch_series` | `series_id`, `start`, `end` |
| `bank` | `list_accounts`, `fetch_transactions` | none; `account_id`, `start`, `end` |

Structural validation checks callable presence and parameter names. Domain services remain responsible for record semantics, persistence, tenant scope, accounting integrity, and bounded provider behavior.

## Provider manifest

Every conforming provider module exports an immutable `ProviderManifest` as `PROVIDER_MANIFEST`.

```python
from apps.provider_sdk import ProviderManifest

__version__ = "0.3.0"

PROVIDER_MANIFEST = ProviderManifest(
    key="market:example_demo",
    name="Example Market Demo",
    version=__version__,
    api_major=0,
    capabilities=("market",),
    description="Deterministic sample market-price adapter.",
    homepage="https://example.invalid/provider",
    license="Apache-2.0",
    network_policy="none",
    credential_env=(),
    data_classification="controlled-sample",
)
```

### Field rules

| Field | Contract |
| --- | --- |
| `key` | Namespaced lowercase key such as `market:example_demo`; current repository keys may use hyphens or underscores in the slug. |
| `name` | Non-empty display name, maximum 128 characters. |
| `version` | Semantic version text such as `0.3.0`. |
| `api_major` | Integer from 0 through 999; must match the application API major. |
| `capabilities` | Unique non-empty subset of `bank`, `fx`, `macro`, `market`, and `tax`; serialized in deterministic sorted order. |
| `factory` | Python identifier naming the synchronous zero-required-argument factory; defaults to `provider`. |
| `sdk_version` | Provider SDK major/minor contract; defaults to the current SDK version. |
| `description` | Optional bounded public description, maximum 512 characters. |
| `homepage` | Optional HTTPS URL, maximum 256 characters. |
| `license` | Optional public license identifier, maximum 64 characters. |
| `network_policy` | `none` or `https`. |
| `credential_env` | Optional unique uppercase environment-variable names. Values are never part of the manifest or evidence. Credentials require `network_policy="https"`. |
| `data_classification` | `controlled-sample`, `public-reference`, or `external-service`. |

Manifest metadata is public review evidence. Do not place tokens, passwords, provider response bodies, private URLs, local paths, tenant identifiers, database details, or secret values in any field.

## Provider factory

The configured factory must be synchronous, callable, and require no arguments.

```python
class ExampleMarketProvider:
    name = "example_market"

    def fetch_prices(self, symbol: str, start: date, end: date) -> list[object]:
        return []


def provider() -> ExampleMarketProvider:
    return ExampleMarketProvider()
```

A structural check does not invoke this factory when the return annotation provides an inspectable provider type. Runtime loading invokes the factory only after the module, manifest, SDK version, API major, configured key, configured capabilities, factory name, and signatures pass.

Factories that are missing, asynchronous, require arguments, raise, return `None`, or return an awaitable fail closed. Failure evidence contains stable check codes and exception classes, not arbitrary exception text.

## Scaffold a provider

The integrated CLI command is:

```powershell
python -m cli.macli provider-sdk scaffold market:example_demo `
  --capability market `
  --name "Example Market Demo" `
  --version 0.3.0 `
  --license Apache-2.0 `
  --network-policy none `
  --data-classification controlled-sample
```

The provider SDK module can also be invoked directly during development:

```powershell
python -m cli.provider_sdk scaffold market:example_demo --capability market
```

The scaffold creates only the known generated files:

```text
src/plugins/market_example_demo/
  __init__.py
  provider.py
  README.md
  tests/
    test_conformance.py
```

Generated content is deterministic, LF-normalized, path-safe, non-networked, and free of machine-specific absolute paths. Without `--force`, any existing generated file blocks replacement. With `--force`, only the known generated files are replaced; unrelated owner files remain untouched.

## Validate providers

Validate one configured provider:

```powershell
python -m cli.macli provider-sdk validate --key market:yfinance
```

Validate an importable module without authorizing it:

```powershell
python -m cli.macli provider-sdk validate --module plugins.market_example_demo.provider
```

Validate every configured provider with deterministic JSON evidence:

```powershell
python -m cli.macli provider-sdk validate --all-configured --format json
```

Structural validation is the default. `--instantiate` additionally calls the synchronous factory and checks the returned instance; it still does not call provider data/network methods.

The command exits with status 1 when any required check fails and status 2 for invalid target selection. JSON output is sorted and bounded. Table output lists check code, status, message, provider module, and final disposition.

## Conformance checks

The evidence can include these stable check families:

- `module.import`
- `manifest.present`
- `manifest.sdk`
- `manifest.api`
- `manifest.key`
- `manifest.capabilities`
- `manifest.version`
- `factory.manifest`
- `factory.callable`
- `factory.sync`
- `factory.signature`
- `factory.result`
- `provider.name`
- `provider.structure`
- `capability.<capability>.<method>`

Warnings do not fail the report. For example, a provider without an inspectable factory return annotation may receive a structural warning; runtime loading then completes instance-level checks. Any `fail` result blocks `load_conforming_provider` and application loading.

## Add a provider to the application

A conforming module remains unauthorized until the application owner adds a `ProviderInfo` entry to `DEFAULT_ALLOWED_PROVIDERS` or the active settings source.

```python
"market:example_demo": ProviderInfo(
    module="plugins.market_example_demo.provider",
    name="Example Market Demo",
    description="Controlled sample market prices for review flows",
    capabilities=("market",),
),
```

The configured key and capabilities must exactly match the manifest. The provider loader checks the allowlist before import and runtime construction. Supplying an import path where a configured key is expected does not bypass the allowlist.

After configuration, add or update:

- bundled-provider conformance policy evidence;
- deterministic unit tests with no live credentials or uncontrolled network calls;
- provider-specific bounded input, output, timeout, retry, and sanitization tests;
- the compatibility matrix;
- relevant setup and operator documentation.

## Network and credential policy

`network_policy="https"` is a declaration, not a networking implementation. Network-backed adapters must still use the repository’s reviewed bounded provider boundary and preserve record, byte, timeout, retry, parameter, and sanitization limits.

Required tests must remain hermetic. Patch or stub all network entry points and prove that structural conformance does not call them. Credentials are supplied by environment or deployment configuration only; manifests list environment-variable **names**, never values.

## Provider SDK versus extensions and marketplace work

- **Provider SDK** — contracts accounting-data adapters consumed by provider-backed services.
- **Operational extensions** — use the separate extension registry for observability, reporting, scenarios, and other optional application behavior.
- **Marketplace or certification program** — does not exist. Package distribution, signatures, attestations, trust tiers, external review, revocation, and production certification require a separate design and owner authorization.

A passing structural report means only that the declared module matches this SDK’s inspected shape. It does not prove data accuracy, accounting correctness, legal compliance, uptime, security of an external service, tenant authorization, production deployment readiness, or regulatory certification.

## Author review checklist

- [ ] Manifest is bounded, public-safe, deterministic, and matches the configured key/capabilities.
- [ ] Factory is synchronous, zero-required-argument, typed, and free of data/network work.
- [ ] Provider name and required capability methods are present.
- [ ] Required parameter names match the contract.
- [ ] Data/network methods preserve repository provider limits and sanitized errors.
- [ ] Tests are deterministic and use no live credentials or uncontrolled network calls.
- [ ] `validate --all-configured --format json` passes.
- [ ] Focused provider and loader tests pass.
- [ ] Full quality, accounting, dependency, secret, Python-matrix, changed-production, and container gates pass on the exact final head.
- [ ] The provider remains disabled unless the application allowlist explicitly permits it.

See [`../provider-compatibility.md`](../provider-compatibility.md), [`../PLUGINS.md`](../PLUGINS.md), and [`../architecture/provider-sdk.md`](../architecture/provider-sdk.md) for the bundled matrix and architectural boundary.
