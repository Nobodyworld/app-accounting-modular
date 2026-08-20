# tests/

Pytest-based regression coverage for the modular accounting platform. Suites are grouped by feature area and mirror the runtime package layout under `src/apps/`, `src/cli/`, and `src/plugins/`.

- API service tests exercise ledger workflows, audit logging, forecast metadata, CLI entry points, and provider-governance persistence/trust-boundary behavior.
- Provider-governance suites prove idempotent bootstrap, allowlist removal, drift quarantine, arbitrary persisted identity rejection, authorization ordering, member/admin separation, revision conflicts, atomic rollback, post-commit cache invalidation, credential-value non-disclosure, deterministic evidence, provenance, and protected Streamlit state clearing without live network access.
- Observability tests assert structured logging and tracing helpers remain stable.
- Smoke tests validate the in-memory SQLModel demo flows.

Run `pytest` or `make ci` to execute the full test matrix. See [docs/operations/automation_playbook.md](../docs/operations/automation_playbook.md) for CI guidance.
