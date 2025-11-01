# docs/reports/

Automated stewardship outputs from `make audit` and related quality gates.

Files are ordered numerically to reflect the audit workflow: context, diagnosis, verification, and Codex trail artifacts.

The latest generated summary is symlinked or copied to `docs/reports/audit-latest.md` during release readiness checks. See [tools/audit_metrics.py](../../tools/audit_metrics.py) for implementation details.
