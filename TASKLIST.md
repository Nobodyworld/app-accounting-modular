# TASKLIST: Active Work

-*NEVER REMOVE SPEC.md, STYLE-GUIDE.md, or TASKLIST.md FROM THE ROOT*

This file is the **authoritative concise active-task list** for this repository. It intentionally does not preserve every historical wish/TODO as unfinished work. Completed implementation history belongs in Git history, `docs/CHANGELOG.md`, release evidence, and closed issues/PRs.

Keep active entries one-line, oldest-first. When completing an active task, check it off and append one indented completion line with the date, PR/issue reference, and result. Do not duplicate an already-completed task as unchecked work.

## Active product validation

- [ ] Run the real human-accountant close pilot using the existing synthetic workflow and record actual usefulness/friction observations (Issue #159; `docs/examples/accountant_close_pilot_review.md`) - TASK-0093 - When completed: _

## Maintenance review dispositions

- [x] Refresh and evaluate Dependabot PR #150 (Ruff/build proposal) from current `main` - TASK-0094 - When completed: 2026-09-13
  - Completed: 2026-09-13 - PR #150 rebased 1 ahead / 0 behind; deferred because the fresh suite fails the deliberate `ruff==0.16.2` migration-policy regression. Adopting Ruff 0.16.6/build 1.6.0 requires a separate intentional tooling-policy migration.
- [x] Refresh and evaluate Dependabot PR #151 (mypy accepted-range expansion into 2.x) from current `main` - TASK-0095 - When completed: 2026-09-13
  - Completed: 2026-09-13 - PR #151 rebased 1 ahead / 0 behind and fresh exact-head validation passed with mypy 2.3.1 across all six required contexts, quality gate, audits, provider-author acceptance, and accounting controls; merge remains an explicit owner decision because the supported range crosses a major version.
- [x] Refresh and evaluate Dependabot PR #152 (pandas accepted-range expansion into 3.x) from current `main` - TASK-0096 - When completed: 2026-09-13
  - Completed: 2026-09-13 - PR #152 rebased 1 ahead / 0 behind but is deferred: changing the runtime requirement invalidates the repository's hash-locked container dependency input digest. A pandas 3.x migration requires an intentional lock regeneration/transitive-compatibility slice and full validation.
- [x] Refresh and evaluate Dependabot PR #153 (Anchore SBOM action 0.24.2) from current `main` - TASK-0097 - When completed: 2026-09-13
  - Completed: 2026-09-13 - PR #153 rebased 1 ahead / 0 behind and all six required contexts pass; existing container build/start/health, least-privilege, lock, SBOM, and evidence contracts remain intact. Technically merge-ready pending owner authorization.

## Current completion boundary

The following major repository slices are complete for the current **Early Beta / Portfolio Preview** scope and must not be re-added as unchecked backlog without a newly demonstrated gap:

- v0.2 Accountant Close Workspace and integrity/evidence corrections;
- v0.3 provider SDK/conformance contract (PR #141);
- v0.4 persistent provider catalog governance (PR #146);
- v0.5 Provider Author Kit (PR #149);
- post-v0.5 review/evidence/workspace-hygiene corrections (PR #154);
- accountant close rehearsal and pilot kit with Windows/browser acceptance (PR #156);
- Close Workspace non-lifecycle refresh, denial-feedback, and active-tab correction (PR #158 / issue #157);
- six-check protected-main enforcement, changed-production coverage, critical-module coverage, container supply-chain evidence, and trusted-main attestations.

If TASK-0093 completes without material product gaps, the repository should be treated as complete for its current portfolio scope after routine maintenance disposition.

## Conditional future scope — not active tasks

Do **not** convert these into active work merely because older reports/TODOs mention them. They require an explicit decision to expand the product/deployment claim:

- Alembic-managed schema migrations and migration bootstrapping before serious persistent or multi-writer deployment.
- Shared/distributed authentication rate limiting and optional MFA before multi-worker/public deployment when required by the threat model.
- Database-native close/posting locks before making multi-writer accounting guarantees.
- Broader deployment observability, PostgreSQL/reverse-proxy/public-hosting acceptance, or production OTLP/alerting examples.
- A production React/web client.
- Provider package publication, marketplace/registry/certification, signing/revocation services, or arbitrary third-party installation.
- Production tax, bank-feed, market-data, treasury, ERP, financial-reporting, or regulatory certification.

Small code-stewardship refactors such as fixture deduplication, broader typing, or additional metrics should be performed only when they materially support an active slice; they are not standalone product obligations.