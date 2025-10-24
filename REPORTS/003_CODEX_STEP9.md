# Codex Chain – Step 9: UX / DX Improvement

## CLI enhancements
- Added a `--format` flag to the demo CLI with JSON/table outputs so engineers
  and stakeholders can pick the most readable format on demand.
- Converted orchestration to `DataSnapshotService.build_snapshot`, surfacing
  validation errors as friendly Click messages rather than stack traces.

## Developer ergonomics
- Extracted reusable table-formatting helpers, enabling future commands to reuse
  consistent output without additional dependencies.
