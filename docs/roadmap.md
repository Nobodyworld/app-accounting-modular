# Roadmap

This roadmap reflects the repository after PR #158 merged to `main` on 2026-09-13. The project remains an **Early Beta / Portfolio Preview** accounting-control toolkit, not a full ERP or production financial platform.

## Current status

| Workstream | Status | Current state | Next meaningful step |
| --- | --- | --- | --- |
| Accounting-control demonstration | Complete for current portfolio scope | Snapshot orchestration, journal controls, scenario plans, CLI/API/Streamlit review surfaces, provenance, diagnostics, and regression evidence are present. | Run the human-accountant pilot in #159 and build only gaps it demonstrates. |
| Accountant Close Workspace | Complete for automated/browser acceptance | Controlled periods, posting gates, reconciliations, variance review, independent journal approvals, checklist/readiness, deterministic evidence, explicit reopen, and refreshed UX are implemented. PR #156 delivered the rehearsal/pilot kit; PR #158 fixed remaining table refresh, denial feedback, and active-tab behavior. | Human usefulness/friction review in #159. |
| Provider SDK and conformance | Complete for v0.3 contract | PR #141 merged bounded manifests, structural contracts, fail-closed conformance, allowlist-enforced loading, scaffolding, CLI evidence, compatibility documentation, and critical coverage. | Preserve compatibility and the executable-trust boundary. |
| Provider catalog governance | Complete for v0.4 contract | PR #146 merged persistent trusted-registration evidence, organization policy/defaults, CAS/audit mutation, allowlist-enforced resolution, API/Streamlit administration, and deterministic secret-free evidence. Persistence narrows but never broadens executable trust. | Maintain `settings.allowed_providers` as the sole executable-code trust source. |
| Provider Author Kit | Complete for v0.5 contract | PR #149 merged the standalone `modular-accounting-provider-sdk`, authoritative in-tree PEP 517 backend, typed scaffold/build/validate tooling, deterministic artifacts, clean-environment acceptance, and the v0.4 governance handoff. | Keep publication/registry/marketplace/certification out of scope unless separately designed. |
| Quality and merge enforcement | Complete for current scope | Six required checks are enforced by ruleset `18912267`: Python 3.12/3.13/3.14, `container-smoke`, `diff-coverage`, and `container-supply-chain`. Post-merge CI for PR #158 (`34738382100`) passed the Python matrix, container supply-chain, accounting controls, and trusted-main attestations. | Preserve the existing gates and conservative workspace hygiene. |
| Work-slice storage hygiene | Complete | Root `AGENTS.md` contains the replacement rules for the closed/superseded PR #147. Ignored status alone never makes local databases, environments, user data, or unknown artifacts disposable. | Preserve the policy; do not reopen #147. |
| Dependency maintenance | Open maintenance only | Dependabot PRs #150-#153 remain separate from product work and were opened before the latest close-pilot merges. | Refresh/re-evaluate each from current `main`; treat major-range proposals conservatively. |
| Human accountant validation | **Not run** | Automated rehearsal, Windows validation, physical-browser acceptance, and UX correction are complete, but no accountant has supplied usefulness/friction observations. | Run issue #159 using the existing synthetic close and reviewer worksheet. |

## Near-term priorities

1. **Run #159, the human-accountant close pilot.** Record actual setup friction, unclear controls, unnecessary role switching, evidence usefulness, and measured workflow time. Do not substitute automated/browser evidence for human judgment.
2. **Fix only demonstrated pilot gaps.** Separate defects from preferences and future ideas; do not broaden accounting policy silently.
3. **Refresh and evaluate Dependabot PRs #150-#153 independently.** Ruff/build and the SBOM action are maintenance; mypy and pandas widen major-version ranges and require explicit compatibility review.
4. **Keep repository status documentation SHA- and state-accurate.** Completed PRs/issues must not remain described as pending or candidate work.
5. If #159 is satisfactory and no material gap remains, treat the repository as **complete for its current portfolio scope** rather than inventing another major feature tranche.

## Conditional future scope — not current obligations

The following work is justified only if the product/deployment claim expands beyond the current local/portfolio boundary:

- Alembic-managed schema migrations and migration bootstrapping before serious persistent or multi-writer deployment.
- Shared/distributed authentication rate limiting and, if required by the deployment threat model, MFA.
- Database-native close/posting locks before making multi-writer accounting guarantees.
- Deployment examples and operational guidance for PostgreSQL, OTLP collectors, Prometheus/Grafana, reverse proxies, or public/LAN hosting.
- Broader strict typing and observability instrumentation as deployment/runtime stewardship work.
- A production web client only after a separate product decision; `apps/react-ui/` remains experimental.

## Explicitly separate product directions

These are **new products or trust models**, not unfinished work in the current repository scope:

- publishing/installing arbitrary third-party provider packages;
- a provider marketplace, remote registry, certification program, trust tiers, signing/revocation service, or vulnerability-response marketplace process;
- production tax, treasury, bank-feed, or market-data certification;
- ERP completeness or commercially supported close certification.

Any such direction requires its own threat model, trust/revocation policy, operating model, acceptance criteria, and explicit owner priority decision.

Roadmap items are directional, not release commitments. Public visibility does not make this project production-ready.