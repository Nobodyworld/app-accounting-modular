# Technical Audit Metrics Snapshot

Generated from the repository state with `src.tools.audit_metrics`.

This file is a stewardship snapshot of package-level trace metrics: executed lines,
missing lines, and the resulting package percentages. It is not the release coverage
gate and should not be compared directly with pytest's aggregate coverage result.

The authoritative CI release gate is:

```text
pytest --cov=src/apps --cov=src/plugins --cov=src/cli --cov-report=term-missing --cov-fail-under=85
```

Use [PUBLIC_RELEASE_AUDIT.md](../../PUBLIC_RELEASE_AUDIT.md) for release-verdict
evidence and hosted CI disposition.

| Package | Trace metric | Executed | Missing |
| --- | ---: | ---: | ---: |
| apps | 68.83% | 7089 | 3210 |
| cli | 64.63% | 581 | 318 |
| plugins | 66.31% | 429 | 218 |
