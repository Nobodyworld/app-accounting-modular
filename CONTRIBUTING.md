# Contributing to Modular Accounting

Thanks for your interest in improving Modular Accounting! This guide outlines the preferred development workflow and contributor expectations.

## Getting Started
1. **Fork the repository** and clone your fork locally.
2. **Install dependencies**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -U pip
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
3. **Install pre-commit hooks**:
   ```bash
   pip install pre-commit
   pre-commit install --install-hooks
   pre-commit install --hook-type commit-msg
   ```
4. **Run the test suite** before submitting changes:
   ```bash
   pytest
   ```

## Branching & Commits
- Use feature branches (`feature/<slug>`, `fix/<slug>`, `chore/<slug>`).
- Follow **Conventional Commits** for all messages. Example: `feat(ledger): add bulk import`.
- Keep commits focused; avoid mixing functional and formatting changes.
- Sign your commits if your organisation requires it.

## Code Style & Linting
- Python code is formatted with **Black** (line length 88) and linted with **Ruff** (including isort rules).
- Markdown/YAML/JSON files are formatted via **Prettier**.
- Static typing is enforced via mypy/pyright (see PLAN.md roadmap).
- Run `pre-commit run --all-files` before pushing to ensure style conformance.

## Testing Strategy
- Prefer unit tests in `tests/` that isolate business logic.
- For API changes, add integration tests covering HTTP contract and schema.
- Provide fixtures or factories for new models and services.
- Ensure new tests are deterministic and hermetic (no live network calls).

## Labels & Issue Triage
- Default labels are defined in [`.github/labels.yml`](.github/labels.yml).
- Tag issues with severity/priority where applicable (`security`, `performance`, `reliability`, `dx`, `documentation`).
- Include owners (`@modular-accounting/<team>`) to route workstreams appropriately.

## Pull Requests
- Link related issues in the PR description.
- Include screenshots or recordings for UI changes (Streamlit).
- Update documentation (README, docs/) alongside code changes.
- CI must be green before requesting review.
- Add a summary to `STATUS.md` after merge per governance checklist.

## Review Process
1. Submit PR → automated checks run.
2. Request review from code owners or relevant domain maintainers.
3. Address feedback with follow-up commits (use `fixup!` for small adjustments).
4. Squash merge using Conventional Commit titles for release notes.

## Reporting Bugs & Requesting Features
- Use the GitHub issue templates (`Bug report`, `Feature request`).
- Provide reproduction steps, expected/actual behaviour, and environment details.
- Tag severity/priority labels where applicable.

We appreciate your contributions and look forward to collaborating!
