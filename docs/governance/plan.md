# Execution Plan

## Milestone 1: Engineering Governance & CI Foundations

### Workstream 1.1: Repository Governance

- **Task**: Establish community health files (CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, support.md, CODEOWNERS) and update README/CHANGELOG scaffolding.
  - **Goal**: Provide clear contribution, support, and security reporting guidance.
  - **Acceptance Criteria**: New docs added with project-specific instructions; README references governance; CHANGELOG adopts semantic-versioning header; no code behavior changes.
  - **Blast Radius**: Documentation only.
  - **Rollback Plan**: Revert documentation commit.
  - **Tags**: {docs, DX, security}.
  - **Status**: ✅ Documentation sweep completed 2024-10-25 adding comprehensive onboarding, architecture, and usage guides.

- **Task**: Add issue/PR templates, label taxonomy, and Conventional Commit guidance.
  - **Goal**: Normalize contribution workflow with templates and commit standards.
  - **Acceptance Criteria**: `.github/ISSUE_TEMPLATE/*.md`, `PULL_REQUEST_TEMPLATE.md`, labels doc, CONTRIBUTING updated with Conventional Commits.
  - **Blast Radius**: Repository meta files.
  - **Rollback Plan**: Remove templates and revert CONTRIBUTING update.
  - **Tags**: {DX, docs}.

### Workstream 1.2: Automation Baseline

- **Task**: Introduce EditorConfig, central Black/Ruff configs, and adopt Prettier for non-Python assets.
  - **Goal**: Enforce consistent formatting.
  - **Acceptance Criteria**: `.editorconfig`, `pyproject.toml` updated, Prettier config added, no source reformat yet.
  - **Blast Radius**: Config files only.
  - **Rollback Plan**: Remove configs.
  - **Tags**: {DX}.

- **Task**: Add pre-commit with Black, Ruff, isort (or Ruff formatter), trailing-whitespace hooks.
  - **Goal**: Local automation for lint/format.
  - **Acceptance Criteria**: `.pre-commit-config.yaml` present; documentation updated with install instructions.
  - **Blast Radius**: Config only.
  - **Rollback Plan**: Delete config and docs.
  - **Tags**: {DX}.

- **Task**: Configure GitHub Actions workflow matrix (lint, type-check placeholder, pytest) with caching, dependency install, artifact upload.
  - **Goal**: Establish continuous integration baseline.
  - **Acceptance Criteria**: `.github/workflows/ci.yml` executes Black/Ruff check, pytest; status badges added to README.
  - **Blast Radius**: CI config.
  - **Rollback Plan**: Disable workflow by deletion.
  - **Tags**: {testing, DX, reliability}.

- **Task**: Add Renovate config and dependency policy documentation.
  - **Goal**: Automate dependency updates.
  - **Acceptance Criteria**: `renovate.json` (or `.json5`) configured with schedules, grouping; README/CONTRIBUTING note added.
  - **Blast Radius**: Config/Docs.
  - **Rollback Plan**: Remove config.
  - **Tags**: {security, DX}.

## Milestone 2: Type Safety & Code Hygiene

### Workstream 2.1: Typing & Lint Strictness

- **Task**: Introduce mypy (or pyright) configuration with strict mode and SQLModel plugin adjustments.
  - **Goal**: Enforce static typing.
  - **Acceptance Criteria**: `mypy.ini` (or pyrightconfig) committed; CI updated to run type checks.
  - **Blast Radius**: Config & CI.
  - **Rollback Plan**: Remove config and revert CI change.
  - **Tags**: {DX, testing}.
  - **Status**: ✅ Baseline mypy config added with strict enforcement for `apps.api.config` and `apps.api.services.forecast_service`; CI hook pending for broader enforcement.

- **Task**: Perform mechanical typing fixes (annotations, TypedDict/Protocol) to satisfy new checker without altering behavior.
  - **Goal**: Zero-warnings typing baseline.
  - **Acceptance Criteria**: mypy passes clean; changes limited to type hints, imports, helper functions; regression tests pass.
  - **Blast Radius**: Low—code annotations only.
  - **Rollback Plan**: Revert offending module or disable rule temporarily.
  - **Tags**: {DX}.
  - **Status**: 🔄 Forecast service deduplication rewritten for type-safety; strict coverage extended to audit, security, database, and dependency helpers with remaining domain services queued for future passes.

### Workstream 2.2: Dead Code Retirement

- **Task**: Identify and remove unused modules/enums/services (e.g., unused AuditAction values, orphan docs) with changelog entry.
  - **Goal**: Reduce maintenance surface.
  - **Acceptance Criteria**: Confirm via `vulture`/`ruff --select=F401,F841` or tests; update docs accordingly.
  - **Blast Radius**: Medium—removal of code paths.
  - **Rollback Plan**: Restore removed modules from history.
  - **Tags**: {DX, performance}.

## Milestone 3: Testing & Quality Gates

### Workstream 3.1: Test Coverage Expansion

- **Task**: Add API contract tests validating OpenAPI schema and key endpoint responses.
  - **Goal**: Protect REST contracts.
  - **Acceptance Criteria**: Tests exercising auth + representative endpoints with schema validation; coverage report generated.
  - **Blast Radius**: Tests only.
  - **Rollback Plan**: Revert new tests.
  - **Tags**: {testing, reliability}.

- **Task**: Introduce CLI snapshot tests (invoke CLI commands via Typer/Click runner) to ensure stable output.
  - **Goal**: Guard CLI behavior.
  - **Acceptance Criteria**: Snapshot files added; CI updated if necessary.
  - **Blast Radius**: Tests.
  - **Rollback Plan**: Remove tests/snapshots.
  - **Tags**: {testing}.

### Workstream 3.2: Coverage & Reporting

- **Task**: Configure pytest coverage (XML/HTML) and integrate coverage badge/upload to CI artifacts.
  - **Goal**: Visibility into coverage levels.
  - **Acceptance Criteria**: Coverage config, CI artifact, README badge.
  - **Blast Radius**: Tooling.
  - **Rollback Plan**: Revert configs.
  - **Tags**: {testing, DX}.

- **Task**: Adopt CodeQL workflow for static analysis (Python) and integrate Gitleaks for secret scanning.
  - **Goal**: Automate SAST and secrets detection.
  - **Acceptance Criteria**: `.github/workflows/codeql.yml`, `.github/workflows/secret-scan.yml`; docs note security reporting path.
  - **Blast Radius**: CI only.
  - **Rollback Plan**: Disable workflows.
  - **Tags**: {security, reliability}.
  - **Status**: Partial. CodeQL workflow configuration exists, but Gitleaks or
    equivalent full-history secret scanning is still required before public
    release.

## Milestone 4: Security, Configuration, and Observability

### Workstream 4.1: Configuration Hardening

- **Task**: Introduce `config/.env.example`, document configuration keys, and add runtime validation using Pydantic Settings with stricter validators.
  - **Goal**: Prevent insecure defaults and misconfiguration.
  - **Acceptance Criteria**: Settings module rejects weak defaults; docs updated.
  - **Blast Radius**: Medium—affects startup config.
  - **Rollback Plan**: Revert settings changes; fallback to previous defaults.
  - **Tags**: {security, reliability, DX}.
  - **Status**: ✅ `config/.env.example`, configuration guide, and hardened validators shipped; monitor for downstream integration feedback.

- **Task**: Add SBOM generation (Syft/CycloneDX) and dependency vulnerability scan in CI.
  - **Goal**: Supply chain transparency.
  - **Acceptance Criteria**: Workflow producing SBOM artifact; docs on retrieval.
  - **Blast Radius**: CI only.
  - **Rollback Plan**: Disable workflow.
  - **Tags**: {security}.

### Workstream 4.2: Observability Enhancements

- **Task**: Implement structured logging (JSON logger, correlation IDs) and propagate through API, scheduler, CLI.
  - **Goal**: Improve debuggability.
  - **Acceptance Criteria**: Logging middleware, scheduler logging, CLI logging harness; tests updated.
  - **Blast Radius**: Medium—affects logging output.
  - **Rollback Plan**: Revert logging module and dependencies.
  - **Tags**: {reliability, DX}.
  - **Status**: ✅ Structured logging pipeline with correlation IDs spans API middleware, scheduler jobs, and CLI commands; Uvicorn loggers unified under the same handlers and async helpers/tests added in `tests/test_observability_logging.py`.

- **Task**: Instrument metrics via OpenTelemetry (FastAPI instrumentation, APScheduler metrics) with optional OTLP endpoint.
  - **Goal**: Enable metrics/tracing integration.
  - **Acceptance Criteria**: Configurable instrumentation behind feature flag; docs for enabling.
  - **Blast Radius**: Medium—optional dependencies.
  - **Rollback Plan**: Disable feature flag, revert instrumentation code.
  - **Tags**: {reliability, performance}.

## Milestone 5: Architecture, Performance, and Release Automation

### Workstream 5.1: Domain Modularisation

- **Task**: Extract repository interfaces for ledger/forecast services (ports/adapters) to decouple from SQLModel.
  - **Goal**: Improve testability and enable alternative storage.
  - **Acceptance Criteria**: Interfaces defined, services refactored to depend on interfaces, unit tests cover new abstractions.
  - **Blast Radius**: High—core service refactor.
  - **Rollback Plan**: Feature flag old behavior; revert if regressions detected.
  - **Tags**: {DX, reliability}.

- **Task**: Introduce feature flags (e.g., via `typing_extensions` Annotated or simple config) for experimental workflows.
  - **Goal**: Enable safe rollout of new slices.
  - **Acceptance Criteria**: Flag library integrated, documentation on toggling, existing features default-enabled.
  - **Blast Radius**: Medium.
  - **Rollback Plan**: Disable flags, revert config.
  - **Tags**: {DX, reliability}.

### Workstream 5.2: Performance & Release

- **Task**: Add benchmark suite (pytest-benchmark) for critical services (forecast generation, report queries) and integrate into CI (non-blocking trend artifact).
  - **Goal**: Track performance regressions.
  - **Acceptance Criteria**: Benchmarks with baseline documentation; CI artifact produced.
  - **Blast Radius**: Tests only.
  - **Rollback Plan**: Remove benchmarks.
  - **Tags**: {performance, testing}.

- **Task**: Containerize API and Streamlit apps with multi-stage Dockerfiles, compose profiles, and GitHub Actions release pipeline (tagged releases → container registry).
  - **Goal**: Provide reproducible builds and automated releases.
  - **Acceptance Criteria**: Dockerfiles, GH workflow for release, signed images (cosign optional), docs for deployment.
  - **Blast Radius**: High—deployment pipeline.
  - **Rollback Plan**: Pause workflow, revert Dockerfiles.
  - **Tags**: {reliability, security, DX}.

- **Task**: Automate semantic versioning (release-please or semantic-release) with CHANGELOG generation.
  - **Goal**: Consistent release notes.
  - **Acceptance Criteria**: Workflow updates changelog on release; instructions in CONTRIBUTING.
  - **Blast Radius**: Docs + CI.
  - **Rollback Plan**: Disable workflow, revert changelog automation.
  - **Tags**: {DX}.

## Sequencing & Dependencies

- Milestone 1 prerequisites: none (foundation work).
- Milestone 2 depends on CI to enforce typing; run sequentially after baseline automation.
- Milestone 3 leverages lint/type gates from Milestone 2.
- Milestone 4 requires governance + CI; configuration hardening should precede observability for consistent settings.
- Milestone 5 builds on prior stability, requires tests/observability to catch regressions.
- Tasks within workstreams can proceed in parallel when blast radius is low, but refactors (Milestone 5) should wait for instrumentation and coverage enhancements.

## Blockers & Assumptions

- Assume continued use of SQLite for local dev; Postgres compatibility to be validated during configuration hardening.
- External API quotas (ECB/Yahoo) may require mocks in tests; ensure integration tests remain offline-friendly.
- Container registry credentials required for release automation (to be provided or replaced with GitHub Container Registry via OIDC).
