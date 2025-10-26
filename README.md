# Modular Accounting

A portable, modular accounting toolkit with pluggable data sources for tax, foreign exchange, and commodity pricing. The project ships with lightweight domain models, adapter contracts, and a demo CLI so teams can stitch together finance workflows without committing to a heavyweight stack.

## What
- **Domain primitives** for money, FX rates, commodity quotes, tax rules, and journal transactions under `apps/modular_accounting/domain`.
- **Adapter contracts** describing how to load tax, FX, and commodity data in `apps/modular_accounting/domain/ports.py` plus in-memory reference implementations in `apps/modular_accounting/adapters`.
- **Snapshot orchestration** service in `apps/modular_accounting/application` that coordinates adapters and returns a consolidated view of rates, quotes, and rules via immutable `SnapshotRequest` payloads.
- **Demo CLI** (`python -m cli.demo_cli snapshot`) that streams adapter output as JSON for quick experiments or integration smoke tests.

## Why
- Keep accounting workflows **portable**: swap adapters without rewriting downstream logic.
- Make integrations **composable**: treat each data source as an interchangeable plugin.
- Provide a **clear starting point** for teams that want to layer tax, FX, or commodities intelligence on top of core ledgers.

## How
1. Install dependencies and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   make install
   ```
2. Run the demonstration CLI to view a consolidated snapshot:
   ```bash
   python -m cli.demo_cli snapshot --base USD --commodity XAU --commodity XAG --format table
   ```
   The `--format` flag toggles between JSON and a friendly ASCII table so you can choose the representation that works best for demos, debugging, or documentation snippets. Input is validated before adapters run to save round trips.
3. Use the operational CLI to build snapshots with real providers (it auto-selects the first configured providers unless you pass explicit overrides such as `--fx-provider`):
   ```bash
   python -m cli.macli snapshot --base USD --commodity XAU --jurisdiction US --format table
   ```
   The command reuses the configured provider plugins, surfaces cache statistics, and prints provider provenance so you can audit inputs. Swap `--format json` to emit a machine-friendly payload that includes cache metrics and request metadata.
4. Implement custom adapters by satisfying the runtime-checkable ports in [`apps/modular_accounting/domain/ports.py`](apps/modular_accounting/domain/ports.py) and wiring them into your own CLI, service, or background job. Compose `SnapshotRequest` instances (or call `DataSnapshotService.build_snapshot`) to pass around snapshot intent. The service ships with thread-safe, TTL-aware caches that prevent duplicate adapter calls, expose hit/miss metrics, and can be disabled when a workload demands fresh data every time.
5. Validate platform health and extension wiring:
   ```bash
   make health          # runs macli health under the hood
   curl http://localhost:8000/health/ready
   ```
6. Scaffold a new extension package with tracing and health hooks:
   ```bash
   python -m cli.macli scaffold-extension reporting:example --directory plugins
   ```
   The command generates a manifest, health probe, and tracing-aware register
   function so you can focus on business logic.
7. Generate an audit snapshot with coverage, complexity, and dependency metrics:
   ```bash
   make audit
   cat REPORTS/audit-latest.md
   ```
   The audit uses `python -m trace` under the hood, making it safe to run in
   restricted environments where `pytest-cov` cannot be installed.

## Documentation
Extended guides live under the [`docs/`](docs/index.md) folder:
- [Setup](docs/setup.md)
- [Architecture overview](docs/architecture.md)
- [Adapter contracts](docs/adapters.md)
- [Examples](docs/examples.md)
- [Roadmap](docs/roadmap.md)
- [Dependency and security posture](docs/DEPENDENCIES.md)
- [High-level architecture map](ARCHITECTURE_OVERVIEW.md)
- [Extension development guide](EXTENSION_GUIDE.md)
- [Automation & agent playbook](AUTOMATION.md)
- [Operations & incident response](docs/operations.md)
- [Agent operations quick reference](AGENTS.md)

## Contributing
Contributions are welcome. Please review the existing governance files (`CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`) before opening a pull request.
