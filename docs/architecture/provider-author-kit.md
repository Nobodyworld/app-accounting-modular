# Provider Author Kit Architecture

Status: implemented v0.5 contract for issue #148. Release claims remain subject to exact-head validation.

## Purpose

The v0.3 provider SDK established bounded manifests, capability contracts, deterministic conformance, scaffolding, and allowlist-enforced application loading. The v0.4 governance layer added persistent organization policy without allowing persistence to broaden executable trust.

v0.5 closes the external-author gap. The authoritative implementation lives in `packages/provider-sdk/src/modular_accounting_provider_sdk`; `apps.provider_sdk` re-exports the same public objects. The repository-owned acceptance harness builds local SDK and provider artifacts, installs them in separate disposable environments with no repository `PYTHONPATH`, blocks network connections during structural validation, proves application packages are absent, and verifies pre-allowlist rejection.

This tranche is an **authoring and packaging boundary**, not a marketplace, package installer, tenant upload surface, registry, certification program, or production provider approval.

## Core decisions

1. The provider SDK becomes one authoritative standalone distribution.
2. The standalone SDK must remain dependency-light and application-independent.
3. `apps.provider_sdk` remains a compatibility facade during v0.5; it must not become a second implementation.
4. A generated provider project is conventionally packageable and installable, but packaging and importability never authorize application execution.
5. `settings.allowed_providers` remains the sole executable-code trust source.
6. v0.4 reconciliation and organization policy remain narrowing controls after operator trust is established.
7. Required authoring and conformance tests remain hermetic and network-free.
8. No package is published by this tranche.

## Target package boundary

The authoritative standalone distribution is:

```text
distribution: modular-accounting-provider-sdk
import:       modular_accounting_provider_sdk
source:       packages/provider-sdk/
```

The exact naming may change only if implementation evidence shows a packaging or namespace conflict. Any change must be documented before code migration.

The standalone package owns:

- immutable provider manifest contracts;
- capability names, protocol shapes, required methods, and parameter maps;
- compatibility parsing and deterministic compatibility results;
- structural conformance checks and bounded reports;
- runtime construction helpers that do not depend on application authorization;
- standalone scaffold generation;
- deterministic author evidence helpers; and
- an SDK-owned author CLI.

The standalone package must not import or depend on:

- FastAPI or Starlette;
- SQLModel or application persistence;
- Streamlit;
- tenant sessions or organization authorization;
- application routers or services;
- provider governance persistence;
- bundled provider implementations;
- scheduler, observability, or accounting workflow services;
- provider-specific network clients; or
- application configuration as an authorization source.

## Layered architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Standalone Provider Author Kit                                      │
│ modular_accounting_provider_sdk                                     │
│ - manifests and capability contracts                               │
│ - conformance and compatibility                                     │
│ - scaffold and author CLI                                           │
│ - deterministic bounded evidence                                    │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ builds/validates only
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Standalone provider project                                         │
│ - pyproject.toml                                                     │
│ - src package                                                        │
│ - PROVIDER_MANIFEST + synchronous factory                           │
│ - deterministic conformance tests                                   │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ wheel/importability do not authorize
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Operator process trust                                              │
│ settings.allowed_providers                                          │
│ - explicit key                                                      │
│ - explicit module                                                   │
│ - explicit capabilities                                             │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ existing allowlist + conformance
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ v0.4 provider governance                                            │
│ - safe registration evidence                                        │
│ - organization enable/disable policy                                │
│ - deterministic capability defaults                                 │
│ - audited revision-protected mutation                               │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ authorized, effective provider
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Accounting application services                                     │
│ - tenant scope and authorization order                              │
│ - provider limits and sanitized errors                              │
│ - accounting semantics, persistence, provenance, and evidence       │
└──────────────────────────────────────────────────────────────────────┘
```

## Compatibility facade

Existing application code and external reviewers currently import `apps.provider_sdk`. v0.5 should preserve that path while making the standalone distribution authoritative.

The preferred migration is:

```text
packages/provider-sdk/src/modular_accounting_provider_sdk/
  authoritative implementation

src/apps/provider_sdk/
  compatibility imports/re-exports only
```

Required invariants:

- manifest and report types have one authoritative definition;
- the facade does not copy or fork implementation logic;
- application callers receive the same contract behavior;
- facade and standalone imports do not create circular imports;
- importing the standalone package does not import the application;
- critical coverage follows authoritative code rather than rewarding duplicate facades;
- removal of the facade requires a later explicit migration decision.

A deprecation warning is not automatically required in v0.5. Warnings that make tests or user workflows noisy should be introduced only with a documented support window and migration path.

## Packaging contract

The SDK distribution must use conventional PEP 517/518 metadata and support deterministic local wheel and source-distribution builds.

At minimum the artifact metadata should define:

- distribution name and semantic version;
- supported Python versions matching the validated matrix;
- license and project metadata;
- minimal runtime dependencies;
- typed package marker when applicable;
- console/module entry point when used;
- package discovery limited to the SDK source tree; and
- explicit exclusion of tests, caches, local evidence, application modules, secrets, and machine-specific paths.

Artifact validation must inspect the actual wheel and sdist contents. A successful build command alone is insufficient.

No v0.5 workflow publishes to PyPI, GitHub Releases, or another registry.

## Standalone author CLI

An author who installs only the SDK artifact should be able to use an SDK-owned command surface, preferably:

```powershell
python -m modular_accounting_provider_sdk scaffold ...
python -m modular_accounting_provider_sdk validate ...
```

A console script may supplement but should not replace the module invocation.

The author CLI should support:

- standalone project scaffolding;
- importable-module validation;
- structural-only validation by default;
- explicit instance construction when requested;
- deterministic table and JSON formats;
- stable exit codes;
- bounded sanitized failures;
- relative evidence paths; and
- no required network access.

The existing `python -m cli.macli provider-sdk ...` surface remains supported and should delegate to shared SDK behavior where possible.

## Standalone project scaffold

The author-facing scaffold should create a conventional project rather than requiring placement under the application `src/plugins` directory.

Target shape:

```text
example-provider/
  pyproject.toml
  README.md
  src/
    <safe_provider_package>/
      __init__.py
      provider.py
      py.typed
  tests/
    test_conformance.py
```

The generated project must:

- derive safe deterministic project and import names from the provider key;
- declare explicit SDK compatibility metadata;
- contain a bounded public manifest;
- contain a typed synchronous zero-required-argument factory;
- generate methods for every selected capability;
- default to non-networked empty-result placeholders;
- build as a wheel and sdist;
- install in a fresh environment;
- validate without the accounting application installed;
- avoid credentials, local paths, tenant identifiers, and machine state;
- preserve unrelated author files during forced regeneration; and
- never generate application allowlist or tenant-governance mutations.

The existing in-repository plugin scaffold may remain as an explicit layout for bundled development, but the two layouts must share templates/contracts rather than drift independently.

## Clean-environment acceptance

The release-authoritative onboarding proof must execute the real artifact path, not merely import the SDK from the repository checkout.

The acceptance harness should:

1. start from the exact repository head;
2. build SDK wheel and sdist;
3. inventory and hash those artifacts;
4. create a disposable author virtual environment;
5. install the built SDK artifact without repository `PYTHONPATH` injection;
6. invoke the standalone scaffold;
7. build the generated provider wheel and sdist;
8. create a separate disposable consumer environment;
9. install the SDK and generated provider artifacts;
10. run generated tests and deterministic conformance;
11. prove no required network call occurred;
12. prove application-only modules are unavailable in the author/consumer environment;
13. prove the installed provider is still unauthorized by the application; and
14. clean disposable environments and build output according to storage-hygiene policy.

Tests that directly import from the source checkout remain useful unit tests but do not satisfy this acceptance boundary.

## Operator handoff

The standalone provider artifact becomes an application candidate only through explicit operator action.

The controlled handoff is:

1. review the provider artifact, manifest, tests, and evidence;
2. install/configure it through an operator-controlled local process;
3. add an explicit key/module/capability tuple to the active `settings.allowed_providers` source;
4. run current conformance against that configured identity;
5. run v0.4 governance reconciliation to persist safe evidence;
6. allow an organization administrator to narrow or default the now-trusted provider; and
7. resolve it at runtime only after tenant authorization and every existing governance/conformance check.

Negative guarantees:

- importability does not imply trust;
- wheel presence does not imply trust;
- a manifest cannot self-authorize;
- an entry point cannot self-authorize;
- persisted registration cannot supply an executable module;
- a tenant API cannot install or introduce a module;
- removing process trust immediately makes historical persistence non-executable.

## Compatibility lifecycle

Three versions remain distinct:

1. **SDK distribution version** — version of the authoring/conformance contract.
2. **Provider implementation version** — semantic version of one provider package.
3. **Application API major** — major version of the application-facing capability contract.

The current exact SDK compatibility behavior should remain until a separately tested bounded range model is implemented. v0.5 must document rather than silently loosen compatibility.

The lifecycle policy should define:

- additive changes that do not invalidate existing providers;
- breaking changes that require an SDK major transition;
- minimum notice and support expectations during Early Beta;
- scaffold version stamping;
- deterministic failure and deprecation codes;
- operator validation of older artifacts;
- security-response exceptions to normal notice periods; and
- the absence of production support or certification promises.

## Evidence model

A deterministic author-kit evidence bundle may include:

- source commit SHA;
- SDK distribution/version;
- Python and build-tool versions;
- SDK wheel/sdist names, inventories, sizes, and SHA-256 hashes;
- generated provider key, package, capabilities, and version;
- provider wheel/sdist names, inventories, sizes, and hashes;
- conformance and compatibility reports;
- clean-environment commands/results;
- operator handoff disposition; and
- cleanup result.

It must not include:

- credentials or raw environment values;
- authorization headers or tokens;
- absolute local paths;
- unrestricted exception messages;
- raw provider data;
- tenant data; or
- claims of marketplace approval, certification, or production readiness.

## Security and supply-chain boundaries

The new package and scaffold expand the build surface but must not expand runtime trust.

Required controls include:

- pinned/reviewed build tooling in release-authoritative environments;
- package metadata validation;
- wheel/sdist inventory checks;
- archive path-traversal checks;
- deterministic hashes;
- dependency audit coverage for the standalone SDK;
- current-tree secret scanning;
- sanitized build and conformance errors;
- no automatic package discovery inside the application; and
- no remote package fetch in required tests.

## Test and quality architecture

At minimum cover:

- standalone import with the application source tree absent;
- package metadata and artifact content;
- wheel and sdist build/install;
- typed package marker;
- facade compatibility and contract identity;
- application dependency leakage prevention;
- standalone CLI success/failure/exit behavior;
- deterministic scaffold output for every capability;
- safe overwrite behavior;
- generated project build/install/conformance;
- compatibility mismatch evidence;
- network-free structural validation;
- package/importability not authorizing runtime loading;
- explicit operator allowlist integration;
- v0.4 reconciliation and process-trust removal behavior;
- deterministic evidence and path/secret sanitization; and
- cleanup of disposable environments.

Authoritative SDK, compatibility, scaffold, CLI, and handoff modules should receive explicit critical line/branch coverage where aggregate coverage could hide trust-boundary gaps.

## Documentation outcome

The completed tranche should provide one clear path for each audience:

- provider author: build/install SDK, scaffold, implement, validate, package, export evidence;
- application operator: review artifact, explicitly configure trust, reconcile, inspect drift;
- organization administrator: narrow trusted provider use and select defaults;
- reviewer: reproduce clean-environment evidence and understand non-goals.

The README, setup guide, SDK guide, architecture overview, compatibility matrix/lifecycle, governance architecture, CLI docs, roadmap, release notes, changelog, and controlled walkthrough must agree on the implemented state.

## Explicit non-goals

v0.5 does not provide:

- a provider marketplace, registry, search index, or certification program;
- package publication or automatic installation;
- entry-point or filesystem auto-discovery;
- tenant-supplied wheels, URLs, modules, factories, or manifests;
- credential storage or brokerage;
- live provider certification tests;
- production provider accuracy/security claims;
- public/LAN deployment approval;
- unrelated dependency-major migrations;
- broad accounting workflow changes; or
- a production web-client rewrite.

## Acceptance boundary

The tranche is complete only when the exact final head proves:

- the standalone SDK package is buildable, installable, typed, bounded, and application-independent;
- a generated standalone provider builds and validates in fresh environments;
- the legacy application import facade remains compatible;
- packaging/importability cannot bypass the operator allowlist;
- v0.4 governance remains a narrowing layer;
- deterministic evidence is secret/path-safe;
- disposable state is cleaned;
- all focused, full, accounting, coverage, typing, dependency, secret, Python-matrix, and applicable container gates pass; and
- no required tool is skipped.
