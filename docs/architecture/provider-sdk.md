# Provider SDK and Conformance Architecture

## Status

This document defines the v0.3 provider SDK and conformance-kit architecture for issue #140. It is an implementation contract, not a marketplace or production-certification claim.

## Goals

The SDK gives provider authors one deterministic path to:

1. declare bounded metadata;
2. implement a supported provider capability;
3. validate structure without live network access;
4. generate machine-readable conformance evidence;
5. request explicit allowlist integration.

The application configuration remains the installation and authorization boundary. A provider manifest can describe a module; it cannot enable itself.

## Package boundary

The public SDK lives under `apps.provider_sdk` and remains dependency-light. It must not import database sessions, tenant models, authentication state, application settings, or provider credentials.

The package contains:

- `contracts.py` — manifest, capability vocabulary, structural protocols, and signature policy;
- `conformance.py` — deterministic structural checks and reports;
- `scaffold.py` — path-safe deterministic provider package generation;
- `__init__.py` — the documented public surface.

## Manifest boundary

Each conforming provider module exposes `PROVIDER_MANIFEST` and a synchronous factory, normally `provider()`.

The immutable manifest records:

- namespaced key;
- display name and implementation version;
- provider-SDK version;
- compatible application API major;
- declared capabilities;
- factory name;
- network policy;
- credential environment-variable names only;
- data classification;
- optional bounded description, homepage, and license metadata.

Credential values, tenant identifiers, request payloads, session data, and arbitrary runtime configuration are prohibited.

## Capabilities

The first SDK contract covers the provider capabilities already represented in the repository:

| Capability | Required callable surface |
| --- | --- |
| `fx` | `sync_daily_rates(base, date_)` |
| `market` | `fetch_prices(symbol, start, end)` |
| `tax` | `upsert_rules()` |
| `macro` | `fetch_series(series_id, start, end)` |
| `bank` | `list_accounts()` and `fetch_transactions(account_id, start, end)` |

Conformance validates structure and parameter names. It does not call provider data methods, perform network access, or certify semantic correctness.

## Conformance behavior

The conformance engine:

- imports only the requested module;
- requires a `ProviderManifest` instance;
- validates manifest bounds and compatibility;
- validates configured key and capability alignment when supplied;
- verifies a synchronous callable factory;
- instantiates the provider once without invoking capability methods;
- requires a non-empty provider `name`;
- verifies required methods and parameter names;
- emits deterministic ordered checks;
- sanitizes import and factory failures;
- returns JSON-compatible evidence;
- fails closed when any required check fails.

The engine must not expose raw exception text because provider exceptions can contain URLs, response bodies, credentials, or upstream payloads.

## Bundled-provider integration

Every configured bundled provider adopts the same manifest contract. The existing configuration allowlist remains authoritative. Loader validation requires the manifest key and capabilities to agree with configuration before a provider is returned to a service.

Provider descriptors may expose manifest and conformance summaries, but no manifest can broaden configured capabilities or bypass tenant authorization.

## Developer workflow

The CLI adds a `provider-sdk` command group:

- `provider-sdk validate` validates an allowlisted key or importable module and supports table or JSON output;
- `provider-sdk scaffold` generates a provider package, README, and conformance test.

Generated files are deterministic, LF-normalized, path-safe, and contain no secrets or local machine paths.

## Security and product boundaries

This tranche does not:

- install arbitrary provider packages;
- create a provider marketplace;
- certify provider financial accuracy;
- permit manifest-driven activation;
- call live networks in required tests;
- alter provider byte, record, timeout, retry, or sanitization limits;
- move authorization after provider discovery;
- change accounting calculations;
- approve LAN or public deployment.

## Evidence

Completion requires focused SDK, loader, scaffold, CLI, and bundled-provider tests; full quality and accounting gates; changed-production coverage; Python 3.12–3.14; container supply-chain and smoke checks; dependency audits; secret scanning; and exact-head connector review.