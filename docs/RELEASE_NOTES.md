# Release Notes

## Current Candidate

Version candidate: `0.2.0`
Current main baseline: `445241b4514baa42feef0541b677233920540114`

This public repository is an Early Beta / Portfolio Preview accounting-controls toolkit. It demonstrates modular snapshot orchestration, authenticated tenant-scoped review utilities, accountant-ready reports, provider provenance, journal controls, health diagnostics, scenario plans, CLI/API/Streamlit review surfaces, and extension contracts. It is not presented as a production ERP, tax engine, treasury system, regulated bank-feed product, or commercially supported accounting platform.

## Highlights

- Authenticated Accountant Close Workspace with immutable lifecycle states, a READY posting freeze, reasoned restart/return-to-work/reopen, typed administrator policy exceptions, ledger-revision-bound reconciliations and current variance runs, explicit journal-approval policy, conditionally persisted draft evidence, and atomic final `CLOSED` evidence.
- Deterministic evidence ZIP with canonical JSON, LF spreadsheet-safe CSV, normalized entry timestamps, per-file SHA-256 values, one non-self-referential manifest hash across bytes/metadata/audit, and typed safe policy output.
- Recorded-evidence download enforcement: generation builds once, while download requires a current persisted manifest and returns a typed conflict for missing, stale, reclassified, or mismatched evidence.
- Bounded close collections with 100-record defaults, 500-record maximum pages, separately paged immutable journal decisions, and a 500-approval per-cycle cap.
- Critical-module coverage policy with independent line and branch floors so aggregate coverage cannot mask close, ledger, workflow, or session-control regressions.

- Public/local Streamlit review flow for financial snapshots, source evidence, freshness, and journal-control status.
- Authenticated organization-scoped scenario-plan, budget, cashflow, FX, and market review workflows.
- Accountant-ready result panels with structured metrics, tables, partial/empty/no-change states, sanitized details, and CSV exports.
- Provider-swappable FX, commodity, tax, market, macroeconomic, and bank-feed demonstration adapters.
- Balanced journal-control examples, account traceability, and authenticated audit attribution.
- Deterministic CLI and API diagnostics for health, telemetry, scenario plans, and extension contracts.
- Prometheus-compatible metrics, request tracing, startup diagnostics, and scheduler health reporting.
- Loopback-only Compose publication with explicit JWT secret configuration.
- Non-root, read-only, capability-dropped container runtime with bounded writable paths.
- Apache-2.0 licensing with `NOTICE`, contribution guidance, security policy, and public audit evidence.

## Latest UX And Security Work

- PR #80 added the authenticated Streamlit utility workspace and shared organization scope.
- PR #88 added deterministic accountant-facing result presentation models.
- PR #89 rendered budget, cashflow, FX, and market result panels with tenant-state isolation.
- PR #92 made the default Compose profile fail closed on JWT configuration and bind host ports to loopback.
- PR #94 bound audit actor identity to the authenticated principal and authorized organization.
- PR #96 hardened both containers with non-root users, read-only root filesystems, capability drops, `no-new-privileges`, and verified writable paths.
- Issue #95 / PR #97 modernizes the remaining Streamlit width API and records responsive/accessibility evidence.
- PR #97 caps accountant-result metrics at two per row after tablet acceptance showed currency values truncating in a four-column row.
- Issue #98 aligns Scenario Plan Review with the existing protected API boundary and clears its rendered result on session changes.

## Validation

The quality gate runs:

- Ruff linting and formatting checks;
- targeted mypy validation;
- full pytest with an aggregate 85% coverage floor;
- focused accounting-control tests;
- `pip check`;
- `pip-audit`; and
- current-tree secret scanning.

The refreshed v0.2 candidate passes 639 tests with 87.99% line coverage
(9,121/10,366) and 71.45% branch coverage (1,829/2,560). All configured
critical-module floors, the 52-test accounting-control subset, `pip check`,
the GitPython 3.1.58 hashed runtime-lock audit, and the development dependency
audit pass. Literal Microsoft Edge 200% zoom remains a manual acceptance gate;
the exact 390×844 Edge viewport, all six close sections, keyboard traversal,
and browser console passed on the refreshed implementation.

Hosted CI additionally validates Python 3.12, 3.13, and 3.14, builds and starts the Compose services, verifies required JWT configuration, and inspects the live least-privilege container runtime. See [`../PUBLIC_RELEASE_AUDIT.md`](../PUBLIC_RELEASE_AUDIT.md) and issue #87 for the current audit disposition.

## Running The Demonstration

Use [`setup.md`](setup.md) for supported local and container workflows. The primary review surfaces are:

- FastAPI service and OpenAPI documentation;
- Streamlit public/local Snapshot Review plus authenticated Scenario Plan Review and utility panels; and
- `cli.macli` operational commands.

Demo providers use controlled sample data unless external credentials are configured.

## Known Limits

- This is a portfolio-grade controls toolkit, not a production accounting system.
- The formal post-UX security audit in issue #87 remains open until the remaining threat-model, route-inventory, input/output, history-scan, static/dynamic, and release-disposition evidence is complete.
- The React directory is experimental and is not part of the validated runtime.
- OTLP export remains optional and requires the OpenTelemetry extras described in the operations documentation.
- Provider catalog persistence and several legacy TODOs remain future work.
- The retained primary screenshot represents the public Snapshot Review flow; it does not depict the authenticated Review Utilities panels.

## Release Decision

The project remains an Early Beta / Portfolio Preview. Local demonstration is the validated deployment boundary. The v0.2 close workspace is not ERP completeness, automatic bank reconciliation, production close certification, public-hosting approval, or regulatory compliance. Trusted-team, LAN, or public hosting claims require a separate deployment review.
