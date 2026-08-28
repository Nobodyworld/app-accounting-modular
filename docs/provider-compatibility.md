# Provider SDK Compatibility Matrix

This matrix documents the v0.5 standalone author kit and the provider contracts declared by the bundled configuration. It is review evidence, not a marketplace listing or production certification.

## Compatibility and deprecation lifecycle

| Identity | Current value | Rule |
| --- | --- | --- |
| SDK distribution | `modular-accounting-provider-sdk==0.5.0` | Author-tool packaging version; local artifacts only in this tranche. |
| SDK import | `modular_accounting_provider_sdk` | Authoritative implementation and public types. |
| Manifest SDK contract | `1.0` | Exact equality is required; no compatibility range is implied. |
| Provider implementation | Manifest semantic version | Provider-owned evidence, independent of the SDK distribution. |
| Application API major | `0` | Exact major equality is required. |
| Scaffold stamp | `0.5.0` | Records which author template produced the project. |

Additive changes must retain existing `1.0` behavior and the facade's object
identity. A breaking manifest or protocol change requires a new contract
version, stable deterministic incompatibility codes, migration guidance, and
an Early Beta notice period when security response does not require immediate
withdrawal. Older artifacts remain valid only when their exact SDK contract and
application API major pass current structural checks. Security fixes may reject
an older artifact immediately and must document the reason.

`apps.provider_sdk` may be removed only after all application callers,
bundled providers, operator commands, downstream examples, and a documented
deprecation window use the standalone import. v0.5 emits no disruptive
deprecation warning. The lifecycle adds no marketplace, certification,
publication, production support, or broad version ranges.

The authoritative installation boundary remains `settings.allowed_providers`. A manifest cannot self-install or self-authorize. Exact-head validation must pass before any branch state is described as validated.

## Application contract

| Contract | Candidate value |
| --- | --- |
| Provider SDK | `1.0` |
| Application API major | `0` |
| Provider implementation version | `0.3.0` |
| Supported capabilities | `bank`, `fx`, `macro`, `market`, `tax` |
| Structural default | No factory invocation when the return type is inspectable; no provider data/network method invocation |
| Runtime loading | Allowlist, manifest, SDK/API, key/capability, factory, provider-name, and signature checks must pass |
| Required test network policy | Hermetic; no live provider calls or credentials |
| Deployment claim | Early Beta / Portfolio Preview; local demonstration only |

## Bundled providers

| Configured key | Import module | Capability | Network policy | Credential environment-variable names | Data classification | Intended role |
| --- | --- | --- | --- | --- | --- | --- |
| `bank:plaid_demo` | `plugins.bank_plaid.provider` | `bank` | `none` | none | `controlled-sample` | Deterministic Plaid-like account and transaction sample data for reconciliation plumbing. |
| `fx:ecb` | `plugins.fx_ecb.provider` | `fx` | `https` | none | `public-reference` | Bounded ECB-style reference-rate adapter through the shared HTTPS provider boundary. |
| `fx:openexchangerates` | `plugins.fx_openexchangerates.provider` | `fx` | `https` | `OPENEXCHANGERATES_APP_ID` | `external-service` | Credentialed bounded OpenExchangeRates adapter. |
| `macro:fred_demo` | `plugins.macro_fred.provider` | `macro` | `none` | none | `controlled-sample` | Deterministic FRED-style macroeconomic series sample data. |
| `market:commodities_demo` | `plugins.market_commodities.provider` | `market` | `none` | none | `controlled-sample` | Deterministic commodity and futures price sample data. |
| `market:yfinance` | `plugins.market_yfinance.provider` | `market` | `https` | none | `external-service` | Bounded high-level Yahoo Finance market-price adapter. |
| `tax:oecd_demo` | `plugins.tax_oecd_stub.provider` | `tax` | `none` | none | `controlled-sample` | Deterministic OECD-style tax-rule sample data. |
| `tax:oecd_vat` | `plugins.tax_oecd_vat.provider` | `tax` | `none` | none | `controlled-sample` | Illustrative VAT-rule sample data for selected OECD jurisdictions. |
| `tax:us_tables` | `plugins.tax_us_tables.provider` | `tax` | `none` | none | `controlled-sample` | Illustrative US federal and state tax-table sample data. |

Every bundled module declares `license="Apache-2.0"`, an API-major value of `0`, and an implementation version of `0.3.0` in this candidate.

## Compatibility interpretation

Provider descriptors expose:

- allowlisted key, display name, description, and configured capabilities;
- import module and implementation version;
- immutable manifest metadata;
- deterministic structural conformance checks;
- application/provider major-version compatibility status.

Compatibility statuses mean:

| Status | Meaning |
| --- | --- |
| `compatible` | Structural conformance passes and the provider implementation major matches the application API major. |
| `incompatible` | Structural conformance fails or the implementation major differs from the application API major. |
| `unknown` | Application or provider version metadata is absent or not parseable. |

A `compatible` descriptor is not proof of provider-data accuracy, service availability, accounting correctness, tenant authorization, security of an upstream service, production deployment readiness, or regulatory compliance.

## Required evidence before integration

A provider change is not complete until the exact final head demonstrates:

1. manifest/configuration key and capability alignment;
2. structural conformance without provider data/network calls;
3. runtime construction through the allowlist boundary;
4. provider-specific bounded input/output, timeout, retry, and sanitized-error behavior;
5. focused SDK, scaffold, CLI, loader, and provider tests;
6. full pytest, accounting controls, aggregate and critical coverage, changed-production coverage, Ruff, format, mypy, dependency audits, and secret scanning;
7. Python 3.12, 3.13, and 3.14 hosted jobs; and
8. applicable container supply-chain and smoke evidence.

## Non-goals

This repository does not currently provide:

- arbitrary package installation;
- automatic manifest discovery or enablement;
- a provider marketplace;
- signed provider distribution or revocation;
- a certification or trust-tier program;
- production bank-feed, tax, market-data, or close-platform approval.

See [`guides/provider_sdk.md`](guides/provider_sdk.md) for authoring and [`architecture/provider-sdk.md`](architecture/provider-sdk.md) for the trust boundary.
