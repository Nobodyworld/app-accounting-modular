<!-- Detected primary: python -->
# URGENT: Repo Standardization Plan (Template)

Use this template to create a repo-local `URGENT.md` when we begin alignment work. Copy into a repo after direction and Master Versions are finalized. Keep tasks ONLY in `TASKLIST.md`.

- Repo: app-accounting-modular
- Maintainers: <owners or CODEOWNERS>
- Contacts: <slack/email>
- Last Updated: <YYYY-MM-DD>

## Summary
## Repo Snapshot
- **Stack**: Python
- **Package Manager**: poetry
- **Lock Files**: 
- **CI Present**: Yes
- **Tests Present**: Yes
- **Binary Files**:  detected
- **Defaults Status**: 

### Repo-Specific Tasks
- Review binary file policy and relocation strategy

## Outputs
- Paste check-only results (lint/format/tests) into the PR.
- Check off items in TASKLIST.md as you complete them.

## Fallback
- If central version targets are unavailable, capture current versions and note 'version snapshot only; awaiting org targets' in the PR.

- Stack classification (choose one primary):
  - [ ] Tauri (Rust + TS + React + Vite)
  - [ ] Electron (Node + TS + React)
  - [ ] React + Vite (SPA/PWA)
  - [ ] Next.js (SSR/ISR)
  - [x] Python service/app
  - [ ] Rust CLI/service
  - [ ] Other: <describe>
- Current CI: <describe workflows/checks>
- Current tests: <frameworks and coverage notes>

## Phase 0 � Audit (read-only)
- Git state clean and fetched: [ ]
- Language(s) and runtime(s): <list>
- Package manager(s): <npm/yarn/pnpm/pip/poetry/go mod/etc>
- Build tooling: <list>
- Lint/format/test: <tools + status>
- CI/CD: <workflows + gates>
- Releases/versioning: <semver/tags/changelog>
- Security: <secret scanning, SAST/DAST, deps scanning>
- Docs: <README, docs/, ADRs>
- License & NOTICE: <files>
- Special notes: <generated code, LFS, submodules, binaries>

## Phase 1 � Defaults (no functional changes)
- [.editorconfig] Add/verify: [x] - EXISTS but incomplete (missing comprehensive language settings from template)
- [.gitattributes] Add/verify: [x] - EXISTS and matches template perfectly
- [.gitignore] Language-appropriate: [ ]
- [CODEOWNERS] Define or confirm: [x] - CONFLICT: Has both root CODEOWNERS (repo-specific rules) and .github/CODEOWNERS (template). Root should be moved to .github/ and merged.
- [CONTRIBUTING.md] Add/refresh: [ ]
- [SECURITY.md] Add/refresh: [ ]
- [PR/Issue templates] Add/refresh: [ ]
- [CI check-only] Lint/format/test baseline: [ ]
- [Pre-commit] Whitespace/EOL/secret scan (check-only): [ ]
- [README] Standard sections present: [ ]

## Conflicts Found
- **CODEOWNERS Conflict**: ✅ RESOLVED - Root CODEOWNERS merged into .github/CODEOWNERS, preserving modular-accounting specific rules and adding standard security/CI/CD rules. Root file removed.
- **.editorconfig Incomplete**: ✅ RESOLVED - Updated to match comprehensive organization template with all language settings.

## Version Alignment Plan
- Refer to the organization-wide Master Versions Record (maintained centrally) for target versions.
- Node (dev tooling):
  - [ ] Align TypeScript/ESLint/Prettier/@typescript-eslint/vitest to org targets.
  - [ ] Re-run lint/format in check-only mode.
- Node (runtime, if applicable):
  - [ ] Review `react`, `vite`, `next`, `zod` against targets, plan upgrades if safe.
- Python:
  - [ ] Align `numpy`, `pandas`, `pydantic`, `fastapi`, `uvicorn`, `requests`, `pyyaml`, `matplotlib`, `scikit-learn`, `prometheus-client`, `torch`, `torchvision`, `streamlit`.
  - [ ] Decide pinned vs compatible specifiers; prefer pinned + lockfile where feasible.
- Rust:
  - [ ] Align key crates (`tauri`, `tokio`, `serde`, `anyhow`) if present.

### Repo-specific deltas vs the organization version targets
- Example: `numpy` current: <x>, target: <y>, action: <pin/upgrade/hold>
- Example: `typescript` current: <x>, target: <y>, action: <pin/upgrade/hold>

## Risks & Constraints
- Potential secret exposure, licensing, binary/LFS concerns, line-endings changes, large diffs. Mitigations: check-only first, small PRs, opt-in auto-fixes later.
- Upgrade risk: run full tests in CI; stage upgrades in small batches.

## Decisions & ADRs
- <Link or inline notes>

## Timeline & Owners
- Target window: <dates>
- Responsible: <name>
- Reviewers: <names>

## Definition of Done (Phase 1)
- Defaults added, CI check-only green.
- Version alignment plan approved (no functional changes yet).
- No behavioral changes introduced.

## Upgrade Playbook (Concise)

- Pre-flight
  - [ ] Create branch `chore/align-versions`
  - [ ] Ensure clean git state and fetched remotes
  - [ ] Open directory `TASKLIST.md` and list upgrade tasks; no other TODO docs

- Node (TypeScript/React/Vite/Next)
  - [ ] Pin dev tooling to the centrally maintained version targets (TypeScript, ESLint, Prettier, @typescript-eslint, Vitest)
  - [ ] Install; run `lint` and `test` in check-only mode; fix config only (no large code changes)
  - [ ] Upgrade runtime libs as needed (react, react-dom, next, vite, zod, router, etc.) to targets
  - [ ] Run `build` and smoke `dev`; address minor type breaks; avoid behavior changes

- Python
  - [ ] Update requirements/pyproject to targets; refresh lock if used
  - [ ] Run tests; fix minimal type/compat issues (pydantic/fastapi/numpy)
  - [ ] Record blockers in `TASKLIST.md`

- Rust
  - [ ] Update crate versions; run `cargo check`, `cargo test`
  - [ ] Fix warnings and minor API changes only

- Wrap-up
  - [ ] Ensure CI check-only passes (lint/format/test/security/license)
  - [ ] Update repo `README` only if necessary
  - [ ] Summarize changes and deltas vs the organization version targets in PR body

## Agent Quickstart

- Do not change behavior; planning and check-only tasks first.
- Always sync first: run the Preflight commands below.
- Prefer small, reviewable changes with clear checklists.

### Preflight
```
git status --porcelain
git fetch --all --prune
```

### Branching & Commits
- Branch: `chore/standards-setup`
- Commits: Conventional Commits (e.g., `chore: add .editorconfig`)

### Commands - Python
```
python -m venv .venv
# Windows
. .venv\Scripts\activate
# Unix
source .venv/bin/activate
pip install --upgrade pip
if exist requirements.txt ( pip install -r requirements.txt )
ruff check . || true
black --check . || true
pytest -q || true
```

### Version Alignment
- Consult the organization-wide version targets (central record) when proposing upgrades.
- Prefer conservative, compatible updates; propose plan before changing major versions.

### PR Checklist (Planning-Only)
- [ ] Defaults verified/added (.editorconfig, .gitattributes, .gitignore, CODEOWNERS, CONTRIBUTING.md, SECURITY.md)
- [ ] CI run locally (check-only) with results pasted in PR
- [ ] Version deltas summarized vs organization targets
- [ ] No functional changes made

## Binary Artifacts
- Do not commit binaries (executables, archives, large models, images/datasets).
- If any are tracked, propose relocating to object storage or Git LFS and add ignore rules.
- List any found binaries in the PR body and add a plan to remove them (planning-only change first).
