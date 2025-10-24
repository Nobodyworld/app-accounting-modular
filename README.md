# Modular Accounting

A portable, modular accounting toolkit with pluggable data sources for tax, foreign exchange, and commodity pricing. The project ships with lightweight domain models, adapter contracts, and a demo CLI so teams can stitch together finance workflows without committing to a heavyweight stack.

## What
- **Domain primitives** for money, FX rates, commodity quotes, tax rules, and journal transactions under `apps/modular_accounting/domain`.
- **Adapter contracts** describing how to load tax, FX, and commodity data plus in-memory reference implementations in `apps/modular_accounting/adapters`.
- **Snapshot orchestration** service that coordinates adapters and returns a consolidated view of rates, quotes, and rules.
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
   pip install -r requirements.txt
   ```
2. Run the demonstration CLI to view a consolidated snapshot:
   ```bash
   python -m cli.demo_cli snapshot --base USD --commodity XAU --commodity XAG
   ```
3. Implement custom adapters by satisfying the protocols in [`apps/modular_accounting/adapters/base.py`](apps/modular_accounting/adapters/base.py) and wiring them into your own CLI, service, or background job.

## Documentation
Extended guides live under the [`docs/`](docs/index.md) folder:
- [Setup](docs/setup.md)
- [Adapter contracts](docs/adapters.md)
- [Examples](docs/examples.md)
- [Roadmap](docs/roadmap.md)

## Contributing
Contributions are welcome. Please review the existing governance files (`CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`) before opening a pull request.
