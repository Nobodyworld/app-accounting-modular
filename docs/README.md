# Modular Accounting Documentation

This directory contains comprehensive documentation for the Modular Accounting platform.

## Overview

Modular Accounting is a portable, modular accounting toolkit with pluggable data sources for tax, foreign exchange, and commodity pricing. The project ships with lightweight domain models, adapter contracts, and a demo CLI so teams can stitch together finance workflows without committing to a heavyweight stack.

## Toolkit Scope

- In scope: accounting snapshot orchestration, provider adapters (FX/commodity/tax), journal and ledger control surfaces, and observability-first operational tooling.
- Out of scope: full ERP coverage, treasury execution workflows, and production-hardened React UI (the React app remains a placeholder scaffold).
- Release readiness is tracked in the public audit log at [../PUBLIC_RELEASE_AUDIT.md](../PUBLIC_RELEASE_AUDIT.md).

## Getting Started

- **[Setup](setup.md)**: Installation, prerequisites, and running tests
- **[Architecture Overview](architecture/overview.md)**: System design and runtime flow
- **[Adapter Contracts](adapters.md)**: Implementing custom data providers
- **[Examples](examples.md)**: Code samples and usage patterns

## Key Components

- **Backend**: FastAPI application with SQLModel and SQLite
- **UI**: Streamlit demonstration interface implemented in `src/apps/web/app.py`
- **Compatibility launcher**: `apps/web/app.py` shims to `src/apps/web/app.py` for tooling and tests
- **React UI**: Experimental placeholder under `apps/react-ui/`
- **Plugins**: Drop-in provider modules for data sources
- **CLI**: Operational commands for snapshots and health checks
- **Extensions**: Optional automation packs with observability

## API Keys & Secrets

- FX providers that call OpenExchangeRates expect `OPENEXCHANGERATES_APP_ID` to be present in the environment. The provider refuses to start without it and never logs the credential.
- Bank feeds (Plaid stub) and macro data providers do not require credentials in this repo; wire real keys via env variables when replacing stubs.
- Prefer `.env` files kept out of version control or a secrets manager in production; avoid baking credentials into CLI flags or config files.

## Documentation Sections

- **[Plugins](PLUGINS.md)**: How to create and integrate data providers
- **[Operations](operations.md)**: Observability, health checks, and incident response
- **[Extension Guide](guides/extension_guide.md)**: Building automation extensions
- **[Roadmap](roadmap.md)**: Future development milestones
- **[Dependencies](DEPENDENCIES.md)**: Package information and security notes

## Governance

- **[Contributing](CONTRIBUTING.md)**: Development workflow and standards
- **[Governance Plan](governance/plan.md)**: Project governance and stewardship
- **[Support](governance/support.md)**: Getting help and incident communication

## Additional Resources

- **[Main README](../README.md)**: Project overview and quickstart
- **[AGENTS.md](AGENTS.md)**: Guidelines for automated contributions
- **[CHANGELOG.md](CHANGELOG.md)**: Release history and changes
- **[Public Release Audit](../PUBLIC_RELEASE_AUDIT.md)**: Authoritative release verdict, hosted CI disposition, and validation evidence
