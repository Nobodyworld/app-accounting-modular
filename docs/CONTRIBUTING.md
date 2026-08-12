# Contributing to Modular Accounting

Thanks for your interest in improving Modular Accounting. This guide outlines the preferred development workflow, contributor expectations, and documentation standards.

## Getting Started

1. **Fork the repository** and clone locally.
2. **Create a virtual environment** and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   make install
   ```

3. **Install pre-commit hooks** for formatting, linting, and commit-message validation:

   ```bash
   pre-commit install --install-hooks
   pre-commit install --hook-type commit-msg
   ```

4. **Run the quality gates** before submitting changes:

   ```bash
   make quality
   ```

## Branching & Commits

- Use feature branches (`feature/<slug>`, `fix/<slug>`, `docs/<slug>`, `quality/<slug>`).
- Follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages (for example, `feat(ledger): add bulk import`).
- Keep commits focused; avoid mixing behaviour changes with mechanical formatting.
- Do not rewrite a shared or already reviewed branch without maintainer approval. Update your branch from its base using the collaboration method agreed for that PR.

## Code Style & Quality Gates

- Python formatting: **Ruff format** (line length 120) enforced via the consolidated quality gate.
- Linting: **Ruff** with project-level configuration in `pyproject.toml`.
- Ruff is pinned exactly to `0.16.0`. The reviewed lint families are explicit, preview behavior is disabled, and Markdown/notebooks are excluded from ordinary Ruff discovery. See the [Ruff 0.16 migration policy](quality/ruff-0.16-migration.md).
- Markdown Python fences are not reformatted by `make quality`; documentation-formatting changes require a separate, intentional proposal.
- Static typing: **mypy** over the configured source packages; new critical modules should be added to meaningful checking.
- Run `pre-commit run --all-files` or `make quality` before pushing. Use `make ci` for the full lint/type/test/security pipeline.
- Public-release and security-review candidates also require full-history secret-scan evidence recorded in [`../PUBLIC_RELEASE_AUDIT.md`](../PUBLIC_RELEASE_AUDIT.md) or the applicable security review.
- Health checks: `make health` exercises the CLI-based readiness probes.
- Steward metrics: `make audit` generates a Markdown snapshot under `docs/reports/` when preparing periodic reviews.

### Changed-production-line coverage

When production code changes, generate coverage and evaluate it against an explicit base commit:

```bash
make diff-coverage BASE=<base-sha-or-ref>
```

The underlying command is:

```bash
python -m src.tools.diff_coverage coverage.json \
  --base <base-sha-or-ref> \
  --head HEAD \
  --config config/diff-coverage.toml \
  --json-output diff-coverage.json \
  --markdown-output diff-coverage.md
```

The policy evaluates changed executable lines under `src/apps`, `src/plugins`, and `src/cli` and requires at least 85% coverage. It is independent of the aggregate 85% line gate and per-critical-module line/branch floors. An unresolved base, malformed evidence, or a changed production file missing from Coverage.py evidence fails closed. Pull-request CI uses the exact GitHub base and head SHAs and uploads deterministic JSON/Markdown evidence.

Generated `coverage.json`, XML, and changed-line evidence are run artifacts; do not commit them.

## Testing Strategy

- Add unit tests under `tests/` using the repository's existing flat naming conventions.
- For API changes, include integration tests using FastAPI's `TestClient` to validate authorization order, status codes, schemas, limits, and sanitized errors.
- CLI commands should have smoke tests using Click's `CliRunner`.
- Keep tests hermetic: no live provider requests, model downloads, or credentials.
- Test accounting and workflow changes for rollback, tenant isolation, boundary values, idempotency, and concurrency where state transitions can race.
- Forecast changes must preserve finite-value, cadence, timezone, regressor-alignment, output, metric, and sanitized-error contracts documented in [`FORECASTING.md`](FORECASTING.md).

## Documentation Expectations

- Every behaviour change must update relevant docs (`README.md`, `docs/`, router/service docstrings).
- Include usage examples or migration notes when introducing endpoints, CLI commands, environment variables, or quality policies.
- Ensure Markdown follows the conventions described in [`README.md`](README.md).
- Changelog entries go under the **Unreleased** section of `CHANGELOG.md`.

## Pull Request Checklist

- [ ] Quality gates pass locally (`make quality`).
- [ ] Changed production code passes `make diff-coverage BASE=<base-sha-or-ref>`.
- [ ] Independent critical-module floors pass.
- [ ] `pre-commit run --all-files` is clean when hooks are installed.
- [ ] Documentation and applicable docstrings are updated and new guides are linked from `docs/README.md`.
- [ ] `CHANGELOG.md` is updated when behaviour changes.
- [ ] Screenshots or browser evidence are attached for material Streamlit/visual changes.
- [ ] Linked issues are referenced in the PR body.

## Review Process

1. Open a PR with a clear title, summary, scope boundary, and validation notes.
2. Required workflows validate Python 3.12–3.14, changed-production coverage, accounting controls, dependency/secret gates, container supply chain, and container smoke as applicable.
3. Address review feedback through focused follow-up commits; do not weaken gates to obtain a passing result.
4. Maintainers use an exact-head squash merge after explicit authorization and green required checks.

CodeQL is not currently an established required workflow for this repository. Do not claim CodeQL evidence unless an actual current scan has run.

## Reporting Bugs & Requesting Features

- Use the GitHub issue templates (`Bug report`, `Feature request`).
- Provide reproduction steps, expected versus actual behaviour, and relevant environment details.
- Never include credentials, tokens, production financial data, or sensitive environment dumps.

Thank you for helping improve this Early Beta modular accounting-control toolkit.
