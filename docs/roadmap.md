# Roadmap

This roadmap reflects the repository state as of August 2026. Dates from the original modernization plan have been replaced with explicit status so completed foundations are not presented as overdue promises.

## Current Status

| Workstream | Status | Current state | Next meaningful step |
| --- | --- | --- | --- |
| Accounting-control demonstration | Complete for portfolio release | Snapshot orchestration, provenance, journal controls, CLI/API/Streamlit review surfaces, examples, and regression coverage are present. | Maintain release evidence and improve reviewer onboarding. |
| Provider SDK and conformance kit | Complete for v0.3 Early Beta | PR #141 merged a public dependency-light SDK, bounded immutable manifests, bank/FX/macro/market/tax structural contracts, fail-closed conformance, allowlist-enforced loading, bundled-provider adoption, deterministic scaffolding, CLI evidence, explicit critical coverage, an author guide, and a compatibility matrix. | Exercise the scaffold from a clean checkout as an external-author onboarding trial and improve compatibility/deprecation guidance from measured evidence. |
| Provider catalog governance | Implemented v0.4 candidate in issue #145 / draft PR #146 | Persistent safe registration evidence, organization enablement/default policy, revision-protected audited mutation, allowlist-enforced runtime resolution, authenticated API/Streamlit administration, operator CLI reconciliation, and deterministic secret-free evidence are implemented. Persistence narrows but never broadens executable trust. | Complete exact-head local and hosted acceptance; keep the draft unmerged until owner review. |
| Provider marketplace | Not implemented | The SDK describes and validates explicitly configured adapters. It does not install packages, auto-enable manifests, distribute providers, or certify third parties. | Keep marketplace/certification out of v0.4; define signing, distribution, trust, review, revocation, vulnerability-response, and operating policy separately before any marketplace work. |
| Workflow recipes | Foundation complete | Scenario plans, preview/inspection commands, sample workflows, orchestration helpers, and an accountant close walkthrough exist. | Add more accountant-oriented recipes only when they reuse validated service contracts and deterministic evidence. |
| Accountant close workspace | Complete for v0.2 Early Beta | Immutable lifecycle states, serialized SQLite period/posting/close gates, authoritative ledger-activity revisions, typed administrator policy exceptions, current variance runs, CAS revisions, bounded evidence, API routes, Streamlit workflow, and literal 200% browser acceptance are present. | Maintain the control boundary; evaluate database-native locks before any multi-writer deployment; do not expand the claim to ERP or production close certification. |
| Quality and forecast robustness | Complete | Repository-owned changed-production coverage, independent critical-module floors, forecast finite-value/cadence/timezone hardening, DST coverage, sanitized API errors, and exact-head Python/container evidence are present. | Maintain the policy and increase floors only when measured evidence supports a deliberate review. |
| Ruff tooling policy | Complete on main; patch maintenance in draft PR #142 | `main` deliberately pins Ruff 0.16.2 with explicit lint selection, Python-only discovery, Markdown exclusion, and executable regression coverage. Draft PR #142 evaluates 0.16.3 under the same policy. | Keep the patch update isolated from product work and unmerged until its remaining local evidence boundary is satisfied and owner authorization is explicit. |
| Observability pack | Foundation complete | Metrics, tracing hooks, health/readiness endpoints, startup diagnostics, scheduler state, and CLI observability commands exist. | Add deployment examples, alerting guidance, and optional OTLP collector integration. |
| Container onboarding | Validated for local demonstration | Digest-pinned API and Streamlit images, hash-locked dependencies, Compose configuration, least-privilege checks, SBOMs, checksums, and trusted-event attestations are present. PR #139 merged the coordinated Python-base, runtime-provider, and tooling maintenance contract. | Maintain one coherent base-image, generator, verifier, lock, test, and documentation contract for every future runtime or image update. |
| Public portfolio release | Public Early Beta | The repository is public with an explicit Early Beta / Portfolio Preview boundary and a completed post-UX code audit. | Maintain accurate release evidence; do not infer LAN or public-hosting approval from repository visibility. |

## Near-term Priorities

1. Complete exact-head acceptance of issue #145 / draft PR #146 and preserve the process allowlist as the sole executable-code trust source.
2. Exercise the v0.3 provider scaffold from a clean checkout as part of external-author onboarding evidence and ensure a generated provider can enter the trusted operator workflow only through explicit process configuration plus conformance.
3. Keep maintenance PR #142 isolated from product work; finish its local clean-environment Ruff 0.16.3 evidence before merge consideration.
4. Consolidate future development-tool dependency changes into deliberate maintenance slices rather than merging partial bot-only major-range proposals without policy/compatibility evidence.
5. Keep setup instructions executable from a clean clone on Windows, macOS, Linux, and Docker.
6. Convert the current source-layout application into a conventionally installable Python project when packaging work begins.
7. Expand strict typing beyond the current targeted modules.
8. Extend the validated v0.2 close controls only through explicit policy decisions and measured critical-module coverage.

## Future Opportunities

- Signed or attestable provider metadata after a separate threat model and operating policy.
- Provider SDK compatibility ranges, deprecation policy, and external author fixtures.
- A separately governed marketplace or certification program only after distribution, trust, review, revocation, and incident-response design.
- Additional jurisdiction-aware tax demonstrations with explicit non-production disclaimers.
- Deployment examples for PostgreSQL, OTLP collectors, and Prometheus/Grafana.
- Database-native close/posting locks before any multi-writer deployment claim.
- A production-grade web client only after the accounting-control workflows and API contracts stabilize.

Roadmap items are directional, not release commitments. Production financial, tax, treasury, market-data, bank-feed, and regulated-data use would require separate control design, security review, compliance assessment, and operational support.
