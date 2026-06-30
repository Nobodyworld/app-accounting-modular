# Repository Specification

- **Repository**: `app-accounting-modular`
- **Maintainers**: Stewardship team (see [docs/governance/support.md](docs/governance/support.md))
- **Last Updated**: 2025-05-24

## Stack Overview

| Layer | Details |
| ----- | ------- |
| Runtime | Python 3.12+ (primary dev on 3.14) |
| Frameworks | FastAPI, SQLModel, Streamlit |
| Tooling | Ruff, Pytest, Makefile-driven quality gates |
| Packaging | PEP 621 via `pyproject.toml` |
| CI | GitHub Actions (lint, tests, release automation) |

## Layout

The repository is organised into documentation-first modules with README files in every directory:

- [`src/apps/`](../src/apps/README.md) – Service packages (API, accounting domain, extensions, observability, web).
- [`src/cli/`](../src/cli/README.md) – Demo and operational CLIs for snapshot orchestration.
- [`docs/`](docs/README.md) – Architecture, governance, operations, and roadmap references.
- [`src/plugins/`](../src/plugins/README.md) – Reference adapters and operational extensions.
- [`tests/`](tests/README.md) – Pytest suites mirroring the runtime packages.
- [`src/tools/`](../src/tools/README.md) – Audit, release, quality gate, and security automation.

See the root [README](README.md#repository-structure) for a tabular map of all directories.

## Key Workflows

- **Install dependencies**: `make install`
- **Static analysis**: `make lint`
- **Health probes**: `make health`
- **End-to-end checks**: `make ci`
- **Audit snapshot**: `make audit` (writes to `docs/reports/`)
- **Release**: `make release PART=<major|minor|patch> MESSAGE="<summary>"`

## Configuration & Environment

- Environment variables documented in [docs/setup.md](docs/setup.md) and mirrored in `.env.example`.
- Default database is SQLite via `DATABASE_URL`; override for Postgres/MySQL as needed.
- Observability tracing bootstrap lives in `apps/observability/tracing/configure_tracing` (see [AGENTS.md](AGENTS.md)).

## Testing Strategy

- Unit and integration tests under `tests/` with pytest fixtures for the CLI, API services, observability, and smoke paths.
- CI runs `make ci`, invoking Ruff, format-check, mypy, pytest, and project-scoped `pip-audit` checks.
- Generated audit artefacts stored in `docs/reports/` and summarised in `CHANGELOG.md` during releases.

## Dependencies & Security

- Requirements tracked in `requirements.txt` and `requirements-dev.txt`.
- Renovate configuration (`renovate.json`) automates dependency update PRs.
- Security policy documented in `SECURITY.md`; responsible disclosure contacts in the same file.

## Documentation Sources

- Central index at [docs/index.md](docs/index.md) with links to setup, architecture, adapters, operations, governance, and roadmap.
- Directory-specific READMEs explain the intent and cross-link to detailed guides.
- Stewardship changes recorded in [docs/governance/stewards_report.md](docs/governance/stewards_report.md).

## Task Management

- All active initiatives tracked in [TASKLIST.md](TASKLIST.md).
- Use the `[priority][estimate]` TODO format described in [AGENTS.md](AGENTS.md) for inline annotations.

## Release Notes

- Follow semantic versioning; record highlights in [CHANGELOG.md](CHANGELOG.md) and [RELEASE_NOTES.md](RELEASE_NOTES.md).
- Version metadata stored in `VERSION`.
