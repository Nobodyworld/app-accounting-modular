# Contributing to Modular Accounting

Thanks for your interest in improving Modular Accounting! This guide outlines the preferred development workflow, contributor expectations, and documentation standards.

## Getting Started
1. **Fork the repository** and clone locally.
2. **Create a virtual environment** and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   make install
   ```
3. **Install pre-commit hooks** for formatting, linting, and commit message validation:
   ```bash
   pre-commit install --install-hooks
   pre-commit install --hook-type commit-msg
   ```
4. **Run the quality gates** before submitting changes:
   ```bash
   make quality
   ```

## Branching & Commits
- Use feature branches (`feature/<slug>`, `fix/<slug>`, `docs/<slug>`).
- Follow [Conventional Commits](https://www.conventionalcommits.org/) for all commit messages (e.g., `feat(ledger): add bulk import`).
- Keep commits focused; avoid mixing behaviour changes with mechanical formatting.
- Rebase before opening a PR to keep history clean.

## Code Style & Quality Gates
- Python formatting: **Black** (line length 88) enforced via pre-commit.
- Linting: **Ruff** (including import sorting) with project-level configuration in `pyproject.toml`.
- Static typing: **mypy** gradually enforced—consult [PLAN.md](PLAN.md) for the current strict coverage map.
- Front-end assets: **Prettier** for Markdown/YAML/JSON.
- Run `pre-commit run --all-files` or `make quality` before pushing to catch style issues locally. Use `make ci` for the full lint/type/test/security pipeline.
- Health checks: `make health` exercises the CLI-based readiness probes.
- Steward metrics: `make audit` generates a Markdown snapshot under `REPORTS/` with
  coverage, complexity, and dependency ratios when preparing quarterly reviews.

## Testing Strategy
- Add unit tests under `tests/` mirroring the module path (`tests/services/test_*.py`, etc.).
- For API changes, include integration tests using FastAPI's `TestClient` to validate status codes, schemas, and metadata.
- CLI commands should have smoke tests using Click's `CliRunner`.
- Keep tests hermetic (no real network calls). Use fixtures/mocks for external APIs.

## Documentation Expectations
- Every code change affecting behaviour must update relevant docs (`README.md`, `docs/`, router/service docstrings).
- Include usage examples or migration notes when introducing new endpoints, CLI commands, or environment variables.
- Ensure Markdown follows the conventions described in `docs/README.md` (tables for configuration, fenced code blocks for commands).
- Changelog entries go under the **Unreleased** section of `CHANGELOG.md`. When shipping a release, run `python -m tools.release <version>` to roll the notes forward automatically.

## Pull Request Checklist
- [ ] Quality gates passing locally (`make quality`).
- [ ] `pre-commit run --all-files` clean.
- [ ] Documentation updated (including docstrings where appropriate) and new
      guides linked from `docs/index.md` when applicable.
- [ ] Added/updated entry in `CHANGELOG.md` if behaviour changed.
- [ ] Screenshots attached for Streamlit/visual changes.
- [ ] Linked issue(s) referenced in the PR body.

## Review Process
1. Open a PR with a clear title, summary, and testing notes (use the PR template).
2. Automated checks (CI, CodeQL) run on every push.
3. Address reviewer feedback via follow-up commits (use `fixup!` or `squash` when appropriate).
4. Maintainers squash-merge once approvals and green checks are in place.

## Reporting Bugs & Requesting Features
- Use GitHub issue templates (`Bug report`, `Feature request`).
- Provide reproduction steps, expected vs actual behaviour, and environment details (OS, Python version, database backend).
- Tag severity/priority labels where applicable and assign to the relevant code owners.

We appreciate your contributions—thank you for helping build a modern, extensible accounting platform!
