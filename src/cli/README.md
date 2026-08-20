# cli/

Command-line entry points that ship with the project.

- `demo_cli.py` – Thin wrapper to exercise adapter orchestration and inspect snapshot payloads.
- `macli.py` – Operational CLI for health, telemetry, snapshots, provider/extension inspection, scenario plans, and scaffolding.
- `provider_sdk.py` – Provider SDK command group for deterministic configured/module conformance evidence, path-safe provider scaffolding, and operator-only governance reconciliation/validation/export. Governance commands persist safe evidence but never accept module paths or install packages. It is mounted as `provider-sdk` under `cli.macli` and may also be invoked directly during isolated SDK development.
- `snapshot_render.py` – Shared helpers for tabular/JSON rendering.

See [`docs/guides/provider_sdk.md`](../../docs/guides/provider_sdk.md) for provider authoring, [`docs/guides/extension_guide.md`](../../docs/guides/extension_guide.md) for extension workflows, and [`README.md`](../../README.md#how) for usage examples.
