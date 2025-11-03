# Modular Accounting Documentation

This directory contains comprehensive documentation for the Modular Accounting platform.

## Overview

Modular Accounting is a portable, modular accounting toolkit with pluggable data sources for tax, foreign exchange, and commodity pricing. The project ships with lightweight domain models, adapter contracts, and a demo CLI so teams can stitch together finance workflows without committing to a heavyweight stack.

## Getting Started

- **[Setup](setup.md)**: Installation, prerequisites, and running tests
- **[Architecture Overview](architecture/overview.md)**: System design and runtime flow
- **[Adapter Contracts](adapters.md)**: Implementing custom data providers
- **[Examples](examples.md)**: Code samples and usage patterns

## Key Components

- **Backend**: FastAPI application with SQLModel and SQLite
- **UI**: Streamlit web interface
- **Plugins**: Drop-in provider modules for data sources
- **CLI**: Operational commands for snapshots and health checks
- **Extensions**: Optional automation packs with observability

## Documentation Sections

- **[Plugins](PLUGINS.md)**: How to create and integrate data providers
- **[Operations](operations.md)**: Observability, health checks, and incident response
- **[Extension Guide](guides/extension_guide.md)**: Building automation extensions
- **[Roadmap](roadmap.md)**: Future development milestones
- **[Dependencies](DEPENDENCIES.md)**: Package information and security notes

## Governance

- **[Contributing](../CONTRIBUTING.md)**: Development workflow and standards
- **[Governance Plan](governance/plan.md)**: Project governance and stewardship
- **[Support](governance/support.md)**: Getting help and incident communication

## Additional Resources

- **[Main README](../README.md)**: Project overview and quickstart
- **[AGENTS.md](../AGENTS.md)**: Guidelines for automated contributions
- **[CHANGELOG.md](../CHANGELOG.md)**: Release history and changes
