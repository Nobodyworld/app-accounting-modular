# tools/

Automation utilities and release helpers used during development.

- `audit_metrics.py` – Generates coverage, complexity, and dependency snapshots surfaced in `docs/reports/`.
- `quality_gate.py` – Compares captured metrics to release thresholds.
- `release.py` / `release_manager.py` – Support the `make release` workflow for semver bumps and changelog updates.

Each script is import-safe; reference [docs/operations/automation_playbook.md](../../docs/operations/automation_playbook.md) for guidance on when to run them.
