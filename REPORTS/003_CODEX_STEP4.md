# Codex Chain – Step 4: Expand Tests & Validation

## Validation upgrades
- `SnapshotRequest.from_primitives` now rejects blank base currency inputs and normalises commodity symbols/jurisdictions, preventing noisy adapter calls.
- Legacy keyword parameters emit deprecation warnings but remain supported, while missing ports raise targeted `TypeError` messages.

## Test coverage additions
- Wrapped legacy keyword scenarios with `pytest.warns` to pin the deprecation contract and error messaging.
- Added regression tests for blank base currency handling and scope de-duplication using a recording commodity adapter to ensure the orchestration layer communicates clean, deterministic inputs.
