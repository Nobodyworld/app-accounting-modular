# Release Notes

## Current Candidate

Version candidate: `0.2.0`
Current main baseline: `4266ea43ed40201388df82bb53f757df45afe204`

This public repository is an Early Beta / Portfolio Preview accounting-controls toolkit. It demonstrates modular snapshot orchestration, authenticated tenant-scoped review utilities, accountant-ready reports, provider provenance, journal controls, health diagnostics, scenario plans, CLI/API/Streamlit review surfaces, extension contracts, and the v0.2 Accountant Close Workspace. It is not presented as a production ERP, tax engine, treasury system, regulated bank-feed product, or commercially supported accounting platform.

## Highlights

- Authenticated Accountant Close Workspace with immutable lifecycle states, a READY posting freeze, reasoned restart/return-to-work/reopen, typed administrator policy exceptions, ledger-revision-bound reconciliations and current variance runs, explicit journal-approval modes, conditionally persisted draft evidence, and atomic final `CLOSED` evidence.
- Deterministic evidence ZIP with canonical JSON, LF spreadsheet-safe CSV, normalized entry timestamps, per-file SHA-256 values, one non-self-referential manifest hash across bytes/metadata/audit, and typed safe policy output.
- Recorded-evidence download enforcement: generation builds once, while download requires a current persisted manifest and returns a typed conflict for missing, stale, reclassified, or mismatched evidence.
- Bounded close collections with 100-record defaults, 500-record maximum pages, separately paged immutable journal decisions, and a 500-approval per-cycle cap.
- Critical-module coverage policy with independent line and branch floors so aggregate coverage cannot mask close, ledger, workflow, or session-control regressions.
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
- Issue #59 is the active reliability tranche for deterministic changed-production-line coverage, the remaining critical-module floors, and forecast finite-value/cadence/timezone hardening.
- Ruff 0.16 remains isolated in issue #102.

## Validation

The quality gate runs:

- Ruff linting and formatting checks;
- targeted mypy validation;
- full pytest with an aggregate 85% coverage floor;
- independent critical-module line and branch floors;
- focused accounting-control tests;
- `pip check`;
- `pip-audit`; and
- current-tree secret scanning.

The merged v0.2 baseline passed 639 tests with 87.97% line coverage
(9,119/10,366) and 71.41% branch coverage (1,828/2,560). All configured
critical-module floors, the 52-test accounting-control subset, `pip check`,
the GitPython 3.1.58 hashed runtime-lock audit, and the development dependency
audit passed. Literal Microsoft Edge 200% zoom acceptance passed in Edge
151.0.4129.72 on Windows 25H2 build 26200.8894: all six close sections,
mutation and download reachability, keyboard traversal, responsive metric and
table layout, and application-origin console checks passed. The exact 390×844
CSS-pixel viewport recheck also passed without page-level horizontal overflow.

Issue #59 introduces a repository-owned changed-production-line policy with an
explicit Git base SHA, deterministic JSON/Markdown evidence, and an 85% floor
that remains independent of the aggregate and per-critical-module gates.

Hosted CI additionally validates Python 3.12, 3.13, and 3.14, builds and starts the Compose services, verifies required JWT configuration, and inspects the live least-privilege container runtime. See [`../PUBLIC_RELEASE_AUDIT.md`](../PUBLIC_RELEASE_AUDIT.md) and the final post-UX audit documentation for the current code-audit disposition.

## Running The Demonstration

Use [`setup.md`](setup.md) for supported local and container workflows. The primary review surfaces are:

- FastAPI service and OpenAPI documentation;
- Streamlit public/local Snapshot Review plus authenticated Scenario Plan Review, Review Utilities, and Accountant Close Workspace; and
- `cli.macli` operational commands.

Demo providers use controlled sample data unless external credentials are configured.

## Known Limits

- This is a portfolio-grade controls toolkit, not a production accounting system.
- The post-UX code audit is complete, but LAN, reverse-proxy, and public-hosting approval remain outside the repository’s default claim.
- The React directory is experimental and is not part of the validated runtime.
- OTLP export remains optional and requires the OpenTelemetry extras described in the operations documentation.
- Provider catalog persistence and several legacy TODOs remain future work.
- The retained primary screenshot represents the public Snapshot Review flow; it does not depict every authenticated workspace.

## Release Decision

The project remains an Early Beta / Portfolio Preview. Local demonstration is the validated deployment boundary. The v0.2 close workspace is not ERP completeness, automatic bank reconciliation, production close certification, public-hosting approval, or regulatory compliance. Trusted-team, LAN, reverse-proxied, or public hosting claims require a separate deployment review.
