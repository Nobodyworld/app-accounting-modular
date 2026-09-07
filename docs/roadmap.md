# Roadmap

This roadmap reflects the repository state after the merged v0.5 Provider Author Kit tranche. Dates from the original modernization plan have been replaced with explicit status so completed foundations are not presented as overdue promises.

## Current Status

| Workstream | Status | Current state | Next meaningful step |
| --- | --- | --- | --- |
| Accounting-control demonstration | Complete for portfolio release | Snapshot orchestration, provenance, journal controls, CLI/API/Streamlit review surfaces, examples, and regression coverage are present. | Exercise the existing controls in a clean accountant-oriented pilot before adding another platform layer. |
| Provider SDK and conformance kit | Complete for v0.3 Early Beta | PR #141 merged a public dependency-light SDK, bounded immutable manifests, bank/FX/macro/market/tax structural contracts, fail-closed conformance, allowlist-enforced loading, bundled-provider adoption, deterministic scaffolding, CLI evidence, explicit critical coverage, an author guide, and a compatibility matrix. | Preserve the v0.3 contracts through the v0.5 compatibility facade. |
| Provider catalog governance | Complete for v0.4 Early Beta | PR #146 merged persistent safe registration evidence, organization enablement/default policy, revision-protected audited mutation, allowlist-enforced runtime resolution, authenticated API/Streamlit administration, operator CLI reconciliation, and deterministic secret-free evidence. Persistence narrows but never broadens executable trust. | Maintain the process allowlist as the sole executable-code trust source and keep evidence exports bound to one consistent service snapshot. |
| Provider Author Kit | Complete for v0.5 Early Beta | PR #149 merged the authoritative in-tree PEP 517 backend, compatibility facade, standalone CLI, typed provider scaffold, wheel/sdist and extracted-source builds, clean installs, metadata/RECORD and path-safety evidence, and the executed allowlist/v0.4/trust-removal handoff. Post-merge CI passed on main. | Keep publication, registry, marketplace, and certification out of scope until a separate product and trust model justifies them. |
| Provider marketplace | Not implemented | The SDK describes and validates explicitly configured adapters. It does not install packages, auto-enable manifests, distribute providers, or certify third parties. | Design distribution, trust, review, revocation, vulnerability-response, and incident-response policy before implementing any marketplace. |
| Workflow recipes | Foundation complete | Scenario plans, preview/inspection commands, sample workflows, orchestration helpers, and an accountant close walkthrough exist. | Validate one clean accountant workflow end to end and build only gaps exposed by that pilot. |
| Accountant close workspace | Complete for v0.2 Early Beta | Immutable lifecycle states, serialized SQLite period/posting/close gates, authoritative ledger-activity revisions, typed administrator policy exceptions, current variance runs, CAS revisions, bounded evidence, API routes, Streamlit workflow, and literal 200% browser acceptance are present. | Run a sanitized historical close through the existing workflow and measure setup friction, missing controls, and reviewer usefulness. |
| Quality and forecast robustness | Complete; merge-enforcement alignment pending | Repository-owned changed-production coverage, independent critical-module floors, forecast finite-value/cadence/timezone hardening, DST coverage, sanitized API errors, and exact-head Python/container evidence are present. Ruleset `18912267` currently requires the three Python build checks and `container-smoke`, but not `diff-coverage` or `container-supply-chain`. | Add both missing check contexts with GitHub Actions integration `15368`, preserving all existing checks, strict up-to-date enforcement, and other protections. |
| Ruff tooling policy | Complete on main; fresh Dependabot proposal open | `main` deliberately pins Ruff 0.16.2 with explicit lint selection, Python-only discovery, Markdown exclusion, and executable regression coverage. The older stale proposal was closed; Dependabot has since opened a fresh minor/patch proposal from the current dependency baseline. | Evaluate the current proposal independently; do not mix it into product or post-v0.5 correction work. |
| Development-tool dependency maintenance | Independent proposals open | Dependabot currently has separate proposals for mypy and other dependencies. They are maintenance work, not blockers for the merged v0.5 product tranche. | Review each from then-current main based on compatibility, security, and policy evidence. |
| Work-slice storage hygiene | Replacement included in post-v0.5 corrections; pending merge | PR #147 is closed without merge. The current correction branch includes root `AGENTS.md` rules protecting pre-existing workspaces and requiring ignored files, databases, user data, and unknown artifacts to be classified before removal. | Validate and land the replacement with the correction slice. Do not reopen or merge the superseded proposal, and never treat Git ignore status as proof that local data is disposable. |
| Observability pack | Foundation complete | Metrics, tracing hooks, health/readiness endpoints, startup diagnostics, scheduler state, and CLI observability commands exist. | Add deployment examples, alerting guidance, and optional OTLP collector integration only when deployment work becomes active. |
| Container onboarding | Validated for local demonstration | Digest-pinned API and Streamlit images, hash-locked dependencies, Compose configuration, least-privilege checks, SBOMs, checksums, and trusted-event attestations are present. PR #139 merged the coordinated Python-base, runtime-provider, and tooling maintenance contract. | Preserve all current workflows until equivalent or stronger required-check enforcement is active; workflow consolidation is separate work. |
| Public portfolio release | Public Early Beta | The repository is public with an explicit Early Beta / Portfolio Preview boundary. The historical public-release audit remains a point-in-time record rather than the current product baseline. | Maintain a concise SHA-bound current acceptance record for major milestones without implying production certification. |

## Near-term Priorities

1. Correct post-v0.5 review findings without reopening completed v0.4/v0.5 delivery work.
2. Preserve `settings.allowed_providers` as the only executable provider trust source; packaging, importability, manifests, entry points, and persistence must never self-authorize.
3. Keep provider-governance evidence secret-free and internally consistent from one service snapshot per export.
4. Add `diff-coverage` and `container-supply-chain` to ruleset `18912267` through an authorized repository-administration action, then read back the complete rule to verify no existing protection changed. The correction branch does not itself modify live repository settings.
5. Land the root `AGENTS.md` replacement for closed PR #147, retaining its rule that ignored databases, environment files, user data, and unknown artifacts require explicit classification before cleanup.
6. Keep active Dependabot work isolated from product and review-correction branches unless a demonstrated security or compatibility requirement makes integration necessary.
7. Run a clean accountant-oriented pilot through the existing close workspace before expanding provider-platform infrastructure.
8. Convert the broader application into a conventionally installable Python project only if that directly improves deployment or user workflows.
9. Extend close controls only through explicit accounting-policy decisions and measured critical-module coverage.

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
