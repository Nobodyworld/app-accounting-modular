# Release Notes

## Unreleased v0.5 Provider Author Kit

The v0.5 tranche introduces the installable, typed, zero-runtime-dependency
`modular-accounting-provider-sdk` distribution; one self-contained authoritative
PEP 517 backend; an identity-preserving `apps.provider_sdk` facade; standalone
scaffold/validate/build CLI commands; conventional provider wheel/sdist
projects; deterministic artifact evidence; and a cross-platform offline
clean-environment acceptance harness.

The harness uses `python -m build`, produces repeatable SDK and provider hashes,
rebuilds extracted sdists, installs wheel/sdist variants in clean environments,
and validates metadata and wheel RECORD entries. Those environments contain no
application package or repository `PYTHONPATH`; structural inspection runs under
a network-denial guard without factory/data calls. The handoff evidence observes
rejection before import, exact operator allowlisting, safe v0.4 reconciliation,
administrator enable/default changes, governed construction, and immediate
non-executability after process-trust removal. Archive/link/path failures and
tenant self-authorization inputs fail closed. No package is published, and this
is not marketplace, registry, certification, production-provider, or public/LAN
deployment approval.

## v0.4 Provider Catalog Governance

v0.4 adds persistent tenant-aware administration on top of the provider SDK while keeping the operator process allowlist authoritative for executable code.

- separate SQLModel records for safe trusted-registration evidence, unique organization provider policy, and unique organization capability defaults;
- deterministic network-free startup/operator reconciliation with drift quarantine, allowlist-removal handling, validation, and secret-free evidence export;
- authenticated member reads and administrator-only revision-protected policy/default mutations with atomic audit evidence;
- allowlist, conformance, compatibility, capability, enablement, and deterministic-default enforcement across authenticated tenant FX, market, tax, and snapshot API paths;
- credential readiness limited to manifest variable names and booleans;
- an accountant/admin Streamlit workspace backed by authoritative API results, with conflict guidance and tenant-state clearing; and
- explicit critical line/branch coverage for the new service, API router, and workspace.

The existing Streamlit Snapshot Review remains a public/local controlled demonstration using safe process-trusted provider descriptors and the local `SnapshotOrchestrator`. It does not consult organization policy/defaults or expose tenant governance, and signing in does not switch its semantics. Provider Governance, Scenario Plan Review, Review Utilities, and tenant API operations remain protected.

This candidate is not a marketplace, package installer, remote registry, provider certification program, credential store, production data certification, ERP expansion, or public/LAN deployment approval. It remains an **Early Beta / Portfolio Preview** for local demonstration.

## Unreleased v0.3 Provider SDK Candidate

Starting `main`: `63da968fcc10c531427a2a58296cb979482d6579`
Draft PR: #141
Issue: #140

The v0.3 candidate adds a dependency-light provider SDK and conformance kit while preserving the repository’s explicit provider allowlist, tenant boundaries, bounded transport controls, and Early Beta / Portfolio Preview claim.

Candidate scope includes:

- immutable bounded provider manifests with SDK/API compatibility, capabilities, factory, network policy, credential environment-variable names, data classification, and public metadata;
- structural contracts for bank, FX, macro, market, and tax providers;
- deterministic fail-closed conformance reports with stable sanitized check codes;
- structural inspection that does not invoke provider data/network methods;
- allowlist-enforced runtime loading with manifest/configuration drift detection;
- manifests and policy evidence for all nine configured bundled providers;
- deterministic provider scaffolding and table/JSON CLI validation;
- targeted mypy and explicit critical line/branch coverage enrollment; and
- a provider author guide, bundled compatibility matrix, architecture record, and corrected provider/extension boundary documentation.

This candidate does not create a marketplace, install arbitrary packages, auto-enable providers, store credentials, broaden network exposure, alter tenant authorization order, rewrite accounting behavior, create a tag/release, or claim production certification.

Exact-head local quality, accounting, changed-production, dependency, secret, Python-matrix, and container validation remains required before the draft PR can be described as merge-ready. Connector-authored branch updates do not by themselves establish hosted CI evidence.

## Last Validated Candidate

Version candidate: `0.2.0`
Pre-maintenance main baseline: `6742be345b3e30635e475392d48cdb3fbeb3f676`

This public repository is an Early Beta / Portfolio Preview accounting-controls toolkit. It demonstrates modular snapshot orchestration, authenticated tenant-scoped review utilities, accountant-ready reports, provider provenance, journal controls, health diagnostics, scenario plans, CLI/API/Streamlit review surfaces, extension contracts, and the v0.2 Accountant Close Workspace. It is not presented as a production ERP, tax engine, treasury system, regulated bank-feed product, or commercially supported accounting platform.

## Highlights

- Authenticated Accountant Close Workspace with immutable lifecycle states, a READY posting freeze, reasoned restart/return-to-work/reopen, typed administrator policy exceptions, ledger-revision-bound reconciliations and current variance runs, explicit journal-approval modes, conditionally persisted draft evidence, and atomic final `CLOSED` evidence.
- Deterministic evidence ZIP with canonical JSON, LF spreadsheet-safe CSV, normalized entry timestamps, per-file SHA-256 values, one non-self-referential manifest hash across bytes/metadata/audit, and typed safe policy output.
- Recorded-evidence download enforcement: generation builds once, while download requires a current persisted manifest and returns a typed conflict for missing, stale, reclassified, or mismatched evidence.
- Bounded close collections with 100-record defaults, 500-record maximum pages, separately paged immutable journal decisions, and a 500-approval per-cycle cap.
- Repository-owned changed-production coverage and independent critical-module line/branch policies so aggregate coverage cannot mask accounting, session, background, provider, forecast, or provider-SDK regressions.
- Forecast finite-value, cadence, timezone/DST, regressor-alignment, output, metric, and sanitized-error contracts.
- Deliberate Ruff 0.16 tooling policy with a current exact 0.16.2 pin, explicit lint families, preview disabled, Python/stub-only discovery, and Markdown/notebook exclusion.
- Public/local Streamlit review flow for financial snapshots, source evidence, freshness, and journal-control status.
- Authenticated organization-scoped scenario-plan, budget, cashflow, FX, market, and close workflows.
- Accountant-ready result panels with structured metrics, tables, partial/empty/no-change states, sanitized details, and CSV exports.
- Provider-swappable FX, commodity, tax, market, macroeconomic, and bank-feed demonstration adapters.
- Balanced journal-control examples, account traceability, and authenticated audit attribution.
- Deterministic CLI and API diagnostics for health, telemetry, scenario plans, and extension contracts.
- Prometheus-compatible metrics, request tracing, startup diagnostics, and scheduler health reporting.
- Loopback-only Compose publication with explicit JWT secret configuration.
- Non-root, read-only, capability-dropped container runtime with bounded writable paths.
- Apache-2.0 licensing with `NOTICE`, contribution guidance, security policy, and public audit evidence.

## Latest UX, Security, And Quality Work

- PR #80 added the authenticated Streamlit utility workspace and shared organization scope.
- PR #88 added deterministic accountant-facing result presentation models.
- PR #89 rendered budget, cashflow, FX, and market result panels with tenant-state isolation.
- PR #92 made the default Compose profile fail closed on JWT configuration and bind host ports to loopback.
- PR #94 bound audit actor identity to the authenticated principal and authorized organization.
- PR #96 hardened both containers with non-root users, read-only root filesystems, capability drops, `no-new-privileges`, and verified writable paths.
- PR #97 modernized Streamlit width usage and recorded responsive/accessibility evidence.
- PR #105 completed the post-UX pre-release code audit and closed issue #87 after all identified findings were remediated.
- PR #124 added the digest-pinned, hash-locked, SBOM-producing, attestable container supply chain.
- PR #126 delivered the v0.2 Accountant Close and Reconciliation Workspace.
- PR #130 delivered deterministic changed-production coverage, the completed critical-module policy, and forecast robustness.
- PR #132 completed the isolated Ruff 0.16 migration without Markdown-wide formatting or product changes.
- PR #135 consolidated the PyJWT and Streamlit compatibility floors, regenerated hashed runtime graph, `actions/attest` update, and pip Dependabot policy.
- PR #139 merged the reviewed Python 3.14.7 slim-trixie base, yfinance 1.5.2 compatibility, deterministic runtime-lock refresh, and Ruff 0.16.2 patch.
- PR #141 is the draft v0.3 provider-SDK and conformance candidate; its merge disposition remains pending exact-head evidence and owner authorization.

## Validation

The quality gate runs:

- Ruff linting and formatting checks;
- targeted mypy validation;
- full pytest with an aggregate 85% coverage floor;
- independent critical-module line and branch floors;
- focused accounting-control tests;
- `pip check`;
- `pip-audit`;
- current-tree secret scanning; and
- verified full-history Gitleaks scanning.

The validated v0.2 maintenance candidate passed 695 tests with 88.00% line coverage
(9,384/10,664) and 71.64% branch coverage (1,927/2,690). All 17 configured
critical-module floors, the 52-test accounting-control subset, `pip check`,
the hashed runtime-lock audit, the development dependency audit, and the
current-tree secret scan passed. Ruff 0.16.2 lint and formatting passed across
247 files, and mypy passed across 69 source files. Changed-production coverage
reported an explicit not-applicable pass because that candidate changed no
configured production source line.

A checksum-verified Gitleaks 8.30.0 binary first detected a runtime-generated
`generic-api-key` canary, then scanned all fetched branches and tags. It
processed 162 commits across 169 reachable commits and seven refs, found zero
leaks, and produced a redacted empty report with SHA-256
`37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`.

Hosted exact-head CI additionally passed Python 3.12, 3.13, and 3.14,
changed-production coverage, API and Streamlit no-cache container builds and
health checks, missing-secret rejection, installed-lock conformance, UID/GID
`10001:10001`, read-only roots, dropped capabilities, `no-new-privileges`,
intended writable paths, SPDX SBOM/checksum evidence, and teardown. PR-event
attestations remain skipped by design; trusted-main attestations run only after
an authorized merge.

These validation figures describe the stated v0.2 maintenance candidate, not the unvalidated v0.3 draft head.

The merged v0.2 browser acceptance remains valid: literal Microsoft Edge 200%
zoom passed in Edge 151.0.4129.72 on Windows 25H2 build 26200.8894 across all
six close sections, mutation and download reachability, keyboard traversal,
responsive metric/table layout, and application-origin console checks. The
exact 390×844 CSS-pixel viewport recheck also passed without page-level
horizontal overflow.

The current Ruff 0.16.2 policy keeps the normal `ruff check .` and `ruff format --check .`
commands while making their file set and lint policy explicit in
`pyproject.toml`. Markdown Python fences remain outside the normal formatter
gate. See [`quality/ruff-0.16-migration.md`](quality/ruff-0.16-migration.md).

See [`../PUBLIC_RELEASE_AUDIT.md`](../PUBLIC_RELEASE_AUDIT.md) and the final post-UX audit documentation for the current code-audit disposition.

## Running The Demonstration

Use [`setup.md`](setup.md) for supported local and container workflows. The primary review surfaces are:

- FastAPI service and OpenAPI documentation;
- Streamlit public/local Snapshot Review plus authenticated Scenario Plan Review, Review Utilities, and Accountant Close Workspace; and
- `cli.macli` operational commands.

Provider authoring and structural review are documented in [`guides/provider_sdk.md`](guides/provider_sdk.md). Demo providers use controlled sample data unless external credentials are configured.

## Known Limits

- This is a portfolio-grade controls toolkit, not a production accounting system.
- The post-UX code audit is complete, but LAN, reverse-proxy, and public-hosting approval remain outside the repository’s default claim.
- The React directory is experimental and is not part of the validated runtime.
- OTLP export remains optional and requires the OpenTelemetry extras described in the operations documentation.
- Provider catalog persistence and several legacy TODOs remain future work.
- Provider SDK conformance is structural; it is not a marketplace, external-service security review, data-accuracy certification, or production approval.
- The retained primary screenshot represents the public Snapshot Review flow; it does not depict every authenticated workspace.

## Release Decision

The project remains an Early Beta / Portfolio Preview. Local demonstration is the validated deployment boundary. The v0.2 close workspace and v0.3 provider-SDK candidate are not ERP completeness, automatic bank reconciliation, production close certification, public-hosting approval, marketplace certification, or regulatory compliance. Trusted-team, LAN, reverse-proxied, or public hosting claims require a separate deployment review.
