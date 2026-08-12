# Release Notes

## Current Candidate

Version candidate: `0.2.0`
Current main baseline: `6742be345b3e30635e475392d48cdb3fbeb3f676`

This public repository is an Early Beta / Portfolio Preview accounting-controls toolkit. It demonstrates modular snapshot orchestration, authenticated tenant-scoped review utilities, accountant-ready reports, provider provenance, journal controls, health diagnostics, scenario plans, CLI/API/Streamlit review surfaces, extension contracts, and the v0.2 Accountant Close Workspace. It is not presented as a production ERP, tax engine, treasury system, regulated bank-feed product, or commercially supported accounting platform.

## Highlights

- Authenticated Accountant Close Workspace with immutable lifecycle states, a READY posting freeze, reasoned restart/return-to-work/reopen, typed administrator policy exceptions, ledger-revision-bound reconciliations and current variance runs, explicit journal-approval modes, conditionally persisted draft evidence, and atomic final `CLOSED` evidence.
- Deterministic evidence ZIP with canonical JSON, LF spreadsheet-safe CSV, normalized entry timestamps, per-file SHA-256 values, one non-self-referential manifest hash across bytes/metadata/audit, and typed safe policy output.
- Recorded-evidence download enforcement: generation builds once, while download requires a current persisted manifest and returns a typed conflict for missing, stale, reclassified, or mismatched evidence.
- Bounded close collections with 100-record defaults, 500-record maximum pages, separately paged immutable journal decisions, and a 500-approval per-cycle cap.
- Repository-owned changed-production coverage and 17 independent critical-module line/branch policies so aggregate coverage cannot mask accounting, session, background, provider, or forecast regressions.
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
- Issue #102 established the isolated Ruff 0.16.0 migration without Markdown-wide formatting or product changes.
- Draft PR #139 contains the coordinated v0.2 maintenance candidate for issue #138: the verified Python 3.14.7 slim-trixie base, YFinance 1.x compatibility and regenerated runtime lock, and the reviewed Ruff 0.16.2 patch. The draft remains unmerged pending review.

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

The merged reliability baseline passed 686 tests with 87.97% line coverage
(9,381/10,664) and 71.55% branch coverage (1,925/2,690). All 17 configured
critical-module floors, the 52-test accounting-control subset, `pip check`,
the hashed runtime-lock audit, the development dependency audit, current-tree
secret scan, and full-history Gitleaks scan passed. Changed-production coverage
was 91.61% (273/298) against the independent 85% floor.

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

Hosted CI additionally validates Python 3.12, 3.13, and 3.14, changed-production coverage, builds and starts the Compose services, verifies required JWT configuration, and inspects the live least-privilege container runtime. See [`../PUBLIC_RELEASE_AUDIT.md`](../PUBLIC_RELEASE_AUDIT.md) and the final post-UX audit documentation for the current code-audit disposition.

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
