# docs/reports/

Automated stewardship outputs from `make audit` and related quality gates.

Files are ordered numerically to reflect the audit workflow: context, diagnosis, verification, and Codex trail artifacts.

The latest generated summary is symlinked or copied to `docs/reports/audit-latest.md` during release readiness checks. See [src/tools/audit_metrics.py](../../src/tools/audit_metrics.py) for implementation details.

Historical `003_CODEX_STEP*.md` files are retained as trail artifacts. Treat
[`../../PUBLIC_RELEASE_AUDIT.md`](../../PUBLIC_RELEASE_AUDIT.md),
[`000_CONTEXT.md`](000_CONTEXT.md), and [`001_DIAGNOSIS.md`](001_DIAGNOSIS.md)
as the current release-readiness sources of truth.
