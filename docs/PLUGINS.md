# Providers and Operational Extensions

Modular Accounting has two separate optional-code boundaries:

- **Providers** supply accounting-related source data such as FX rates, market prices, tax rules, macroeconomic series, or bank-feed records.
- **Operational extensions** add optional application behavior such as reporting, scenarios, analytics, or observability.

They are not interchangeable. Providers use the public `apps.provider_sdk` contract and remain subject to the explicit provider allowlist. Operational extensions use the existing extension registry and lifecycle. Neither boundary is a marketplace, an arbitrary package installer, or a production certification program.

The repository remains an **Early Beta / Portfolio Preview** validated for local demonstration.

## Provider boundary

Provider modules are authorized only when `settings.allowed_providers` maps a configured key to an import module and capabilities. Importable code is not automatically discovered or enabled.

Each conforming provider module declares:

- a bounded immutable `PROVIDER_MANIFEST`;
- a synchronous zero-required-argument factory, normally `provider`;
- a non-empty provider instance name; and
- one or more supported capability method shapes.

Supported provider capabilities are:

| Capability | Required methods |
| --- | --- |
| `fx` | `sync_daily_rates` |
| `market` | `fetch_prices` |
| `tax` | `upsert_rules` |
| `macro` | `fetch_series` |
| `bank` | `list_accounts`, `fetch_transactions` |

Structural conformance validates module import, manifest type, SDK version, API-major compatibility, configured key/capability alignment, factory shape, provider name, and required signatures. It does not invoke provider data/network methods.

Runtime loading occurs only after the allowlist and all required conformance checks pass. A provider manifest is descriptive metadata; it cannot authorize installation, tenant access, database access, credentials, or network privileges.

## Provider commands

Validate one configured provider:

```powershell
python -m cli.macli provider-sdk validate --key fx:ecb
```

Validate every configured provider and emit deterministic JSON:

```powershell
python -m cli.macli provider-sdk validate --all-configured --format json
```

Inspect an importable module without adding it to the allowlist:

```powershell
python -m cli.macli provider-sdk validate --module plugins.market_example_demo.provider
```

Scaffold a provider package:

```powershell
python -m cli.macli provider-sdk scaffold market:example_demo --capability market
```

During isolated SDK development, the command group can also be invoked with `python -m cli.provider_sdk`.

See:

- [`guides/provider_sdk.md`](guides/provider_sdk.md) for the author workflow;
- [`provider-compatibility.md`](provider-compatibility.md) for the bundled contract matrix; and
- [`architecture/provider-sdk.md`](architecture/provider-sdk.md) for the trust boundary.

## Bundled provider catalog

The default configuration includes controlled-sample and bounded external-service adapters across bank, FX, macro, market, and tax capabilities. The compatibility matrix is the readable inventory; `apps.api.config.DEFAULT_ALLOWED_PROVIDERS` remains the authoritative configured list.

Bundled provider tests prove that:

- every configured key has a corresponding manifest;
- manifest keys and capabilities match configuration;
- structural conformance does not call network entry points;
- provider descriptors expose manifest and conformance evidence; and
- network policy, credential environment-variable names, and data classification remain explicit.

Credential values, tenant identifiers, local paths, raw upstream responses, and provider exception text must not appear in manifests or conformance evidence.

## Provider development rules

A provider contribution must:

1. preserve the configuration allowlist as the installation boundary;
2. keep the factory free of data/network work;
3. use deterministic tests without live credentials or uncontrolled network calls;
4. preserve established byte, record, date-range, timeout, retry, validation, and sanitization limits;
5. add provider-specific success and failure-path tests;
6. update the compatibility matrix and author documentation; and
7. pass the exact-head Python, accounting, coverage, dependency, secret, and container gates.

Do not auto-enable a provider because its module imports or its manifest validates.

## Operational extensions

Operational extensions remain under `apps.extensions` and the extension loader. They are suitable for optional reporting, scenarios, analytics, observability, and operations behavior that does not belong in an accounting-data provider.

Current configuration may include enabled or disabled extension entries. Extension discovery and lifecycle are documented in [`guides/extension_guide.md`](guides/extension_guide.md). An extension must not bypass authentication, tenant scope, audit identity, accounting services, or provider limits.

## Choosing the correct boundary

Use a **provider** when the component supplies bounded source records consumed by accounting services.

Use an **extension** when the component adds optional application behavior without acting as a source-data adapter.

Use neither when the proposal requires arbitrary package installation, public marketplace operations, credential brokering, code execution from user uploads, a certification program, or production deployment claims. Those require separate design, threat modeling, operating controls, and explicit owner authorization.

## Security and deployment limits

- Required tests are hermetic and non-networked.
- Network-backed providers must use HTTPS and preserve the shared bounded transport policy.
- Manifests may list credential environment-variable names only.
- Providers do not receive authenticated sessions or tenant context through the SDK contract.
- Provider results still pass through application services, tenant controls, accounting integrity checks, provenance, and audit boundaries.
- A passing conformance report is structural evidence, not proof of data accuracy, legal compliance, upstream security, production readiness, or regulatory certification.
- The default application and containers remain loopback-only and locally demonstrated.
