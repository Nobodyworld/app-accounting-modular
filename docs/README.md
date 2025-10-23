# Modular Accounting Documentation

This directory collects deep-dive references for core platform areas—architecture, configuration, forecasting, plugins, AI integrations, and the tax domain model. Each guide is written for engineers onboarding to the codebase as well as operators deploying the stack in production.

## Navigating the Docs
| Guide | Description |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | High-level system and data-flow overview including scheduler, observability, and plugin lifecycle diagrams. |
| [CONFIGURATION.md](CONFIGURATION.md) | Runtime settings, environment variables, and deployment hardening recommendations. |
| [FORECASTING.md](FORECASTING.md) | Forecasting and budgeting workflows, API/CLI entry points, and diagnostics artefacts. |
| [PLUGINS.md](PLUGINS.md) | Provider contracts, discovery process, and packaging guidance for custom integrations. |
| [AI_INTERFACE.md](AI_INTERFACE.md) | How external agents and automation frameworks should authenticate and interact with the platform. |
| [TAX_MODEL.md](TAX_MODEL.md) | Domain-specific schema for tax rules and jurisdiction metadata. |

## Quick Orientation
- **Start here** if you are new to the platform: read [ARCHITECTURE.md](ARCHITECTURE.md) for component responsibilities, then scan [CONFIGURATION.md](CONFIGURATION.md) to bootstrap credentials and runtime settings.
- **Extending the system**: build providers following [PLUGINS.md](PLUGINS.md); wire their configuration using the environment variable tables in [CONFIGURATION.md](CONFIGURATION.md).
- **Automating workflows**: combine REST examples from [AI_INTERFACE.md](AI_INTERFACE.md) with CLI commands described in [FORECASTING.md](FORECASTING.md) and [docs/PLUGINS.md](PLUGINS.md).
- **Understanding compliance surfaces**: [TAX_MODEL.md](TAX_MODEL.md) documents jurisdictional rules and planned enhancements.

## Documentation Style
All guides follow these conventions:
- Concise introductions outlining the problem the component solves.
- Step-by-step usage sections with copy-pastable code blocks (`curl`, CLI, or Python snippets).
- Architecture diagrams using ASCII or Mermaid syntax to make data flow explicit.
- Callouts for TODOs and roadmap items that reference existing code comments when relevant.

If you spot stale content or missing context, open an issue or PR—documentation maintenance is part of the Definition of Done for every change touching the affected component.
