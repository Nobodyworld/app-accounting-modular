# Roadmap

This roadmap reflects the repository state as of August 2026. Dates from the original modernization plan have been replaced with explicit status so completed foundations are not presented as overdue promises.

## Current Status

| Workstream | Status | Current state | Next meaningful step |
| --- | --- | --- | --- |
| Accounting-control demonstration | Complete for portfolio release | Snapshot orchestration, provenance, journal controls, CLI/API/Streamlit review surfaces, examples, and regression coverage are present. | Maintain release evidence and improve reviewer onboarding. |
| Provider SDK and conformance kit | Complete for v0.3 Early Beta | PR #141 merged a public dependency-light SDK, bounded immutable manifests, bank/FX/macro/market/tax structural contracts, fail-closed conformance, allowlist-enforced loading, bundled-provider adoption, deterministic scaffolding, CLI evidence, explicit critical coverage, an author guide, and a compatibility matrix. | Preserve the v0.3 contracts while v0.5 moves the authoritative authoring surface into a standalone installable SDK distribution with a compatibility facade. |
| Provider catalog governance | Complete for v0.4 Early Beta | PR #146 merged persistent safe registration evidence, organization enablement/default policy, revision-protected audited mutation, allowlist-enforced runtime resolution, authenticated API/Streamlit administration, operator CLI reconciliation, and deterministic secret-free evidence. Persistence narrows but never broadens executable trust. | Maintain the process allowlist as the sole executable-code trust source and require v0.5 external artifacts to enter through the same explicit operator and governance boundary. |
| Provider Author Kit | Active v0.5 tranche in issue #148 | The current scaffold and conformance engine work inside the application source tree, but a clean external author cannot yet install a standalone SDK artifact, generate a conventional provider project, build/install it in isolated environments, and produce operator handoff evidence without application imports. | Deliver the installable SDK package, standalone author CLI and scaffold, clean-environment acceptance, compatibility/deprecation lifecycle, and allowlist-first v0.4 handoff proof as one coherent slice. |
| Provider marketplace | Not implemented | The SDK describes and validates explicitly configured adapters. It does not install packages, auto-enable manifests, distribute providers, or certify third parties. | Keep marketplace, registry, publishing, signing, certification, remote discovery, and automatic installation out of v0.5. |
| Workflow recipes | Foundation complete | Scenario plans, preview/inspection commands, sample workflows, orchestration helpers, and an accountant close walkthrough exist. | Add more accountant-oriented recipes only when they reuse validated service contracts and deterministic evidence. |
| Accountant close workspace | Complete for v0.2 Early Beta | Immutable lifecycle states, serialized SQLite period/posting/close gates, authoritative ledger-activity revisions, typed administrator policy exceptions, current variance runs, CAS revisions, bounded evidence, API routes, Streamlit workflow, and literal 200% browser acceptance are present. | Maintain the control boundary; evaluate database-native locks before any multi-writer deployment; do not expand the claim to ERP or production close certification. |
| Quality and forecast robustness | Complete | Repository-owned changed-production coverage, independent critical-module floors, forecast finite-value/cadence/timezone hardening, DST coverage, sanitized API errors, and exact-head Python/container evidence are present. | Maintain the policy and increase floors only when measured evidence supports a deliberate review. |
| Ruff tooling policy | Complete on main; patch maintenance in draft PR #142 | `main` deliberately pins Ruff 0.16.2 with explicit lint selection, Python-only discovery, Markdown exclusion, and executable regression coverage. Draft PR #142 evaluates 0.16.3 under the same policy. | Keep the patch update isolated from product work and unmerged until its remaining local evidence boundary is satisfied and owner authorization is explicit. |
| Development-tool dependency maintenance | Isolated proposals open | PRs #143 and #144 are major-range pytest-cov and mypy proposals. They are not product work and must not be absorbed into v0.5 without a deliberate compatibility/policy slice. | Evaluate or supersede them separately after exact current-main compatibility evidence. |
| Work-slice storage hygiene | Documentation proposal open | PR #147 proposes repository-level worktree and temporary-workspace cleanup rules. | Keep it isolated from v0.5 and reconcile it separately so product delivery does not inherit unrelated branch history. |
| Observability pack | Foundation complete | Metrics, tracing hooks, health/readiness endpoints, startup diagnostics, scheduler state, and CLI observability commands exist. | Add deployment examples, alerting guidance, and optional OTLP collector integration. |
| Container onboarding | Validated for local demonstration | Digest-pinned API and Streamlit images, hash-locked dependencies, Compose configuration, least-privilege checks, SBOMs, checksums, and trusted-event attestations are present. PR #139 merged the coordinated Python-base, runtime-provider, and tooling maintenance contract. | Maintain one coherent base-image, generator, verifier, lock, test, and documentation contract for every future runtime or image update. |
| Public portfolio release | Public Early Beta | The repository is public with an explicit Early Beta / Portfolio Preview boundary and a completed post-UX code audit. | Maintain accurate release evidence; do not infer LAN or public-hosting approval from repository visibility. |

## Near-term Priorities

1. Deliver issue #148 as one v0.5 Provider Author Kit tranche: standalone SDK distribution, standalone scaffold/CLI, clean-environment wheel/sdist proof, compatibility lifecycle, deterministic evidence, and explicit v0.4 operator handoff.
2. Preserve `settings.allowed_providers` as the only executable provider trust source; packaging, importability, manifests, entry points, and persistence must never self-authorize.
3. Reconcile stale v0.4 candidate/draft wording across documentation while implementing v0.5; do not create a separate cosmetic release-state PR.
4. Keep maintenance PRs #142, #143, #144, and documentation PR #147 isolated from the product branch.
5. Keep setup and authoring instructions executable from clean Windows, macOS, Linux, and container-compatible environments where applicable.
6. Convert the broader application into a conventionally installable Python project only after the standalone SDK package boundary is proven; do not force all application packaging into v0.5.
7. Expand strict typing beyond the current targeted modules only when it directly supports the package, compatibility, or trust boundary under review.
8. Extend the validated v0.2 close controls only through explicit policy decisions and measured critical-module coverage.

## Future Opportunities

- Bounded provider SDK compatibility ranges after the exact-version lifecycle is documented and tested.
- Signed or attestable provider metadata after a separate threat model and operating policy.
- A separately governed marketplace or certification program only after distribution, trust, review, revocation, vulnerability-response, and incident-response design.
- Conventional installation of the full accounting application after the standalone SDK packaging boundary is stable.
- Additional jurisdiction-aware tax demonstrations with explicit non-production disclaimers.
- Deployment examples for PostgreSQL, OTLP collectors, and Prometheus/Grafana.
- Database-native close/posting locks before any multi-writer deployment claim.
- A production-grade web client only after the accounting-control workflows and API contracts stabilize.

Roadmap items are directional, not release commitments. Production financial, tax, treasury, market-data, bank-feed, regulated-data, provider-distribution, and certification use would require separate control design, security review, compliance assessment, and operational support.
