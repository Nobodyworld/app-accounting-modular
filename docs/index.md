# Documentation Index

Welcome to the Modular Accounting documentation. The guides below walk through
setup, architecture, adapter design, practical examples, and the forward-looking
roadmap.

- [Setup](setup.md) – install dependencies, run tests, and execute the demo CLI.
- [Architecture Overview](architecture/overview.md) – visualise the layered design and
  understand how requests flow through ports and adapters.
- [System Map](architecture/overview.md) – top-level runtime surfaces and
  operational safeguards introduced in Stage 3.
- [API Reference](api.md) – REST API endpoints and integration guide.
- [Adapter Contracts](adapters.md) – implement custom providers that satisfy the
  runtime-checkable protocols.
- [Examples](examples.md) – copy-paste ready commands and snippets for common
  tasks.
- [Foreign Currency Case Study](examples/foreign_currency_accounting_case_study.md) –
  end-to-end journal controls for a multi-currency purchase and month-end revaluation.
- [Extension Guide](guides/extension_guide.md) – build and register optional
  automation packs with health probes and metrics.
- [Operations & Incident Response](operations.md) – observability, tracing, and
  recovery playbooks for operators and agents.
- [Roadmap](roadmap.md) – upcoming milestones and strategic investments.
- [Dependencies](DEPENDENCIES.md) – pinned packages, license posture, and
  security review notes.
- [Governance plan](governance/plan.md) – contributor expectations and
  prioritised initiatives tracked by the stewardship team.
- [Stewardship report](governance/stewards_report.md) – quarterly metrics,
  audit results, and automation handover notes.
- [Support channels](governance/support.md) – where to request help and follow
  incident communications.
- [Directory overviews](../README.md#repository-structure) – quick links to
  per-folder READMEs (architecture, governance, operations, plugins, tests).
- [Public Release Audit](../PUBLIC_RELEASE_AUDIT.md) – release gate evidence,
  path validation, and clean-clone verification notes.
