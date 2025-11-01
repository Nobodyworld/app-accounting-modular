# Codex Chain – Step 2: Clean & Organize

## Refactoring focus
- Normalised `SnapshotRequest` collections to tuples and introduced the `from_primitives` constructor so orchestration input handling lives in a single, easily-testable location.
- Added an internal `_resolve_tax_rules` helper and `_choose_port` factory to `DataSnapshotService` to clarify responsibilities and preference rules between modern and legacy adapter arguments.

## Structure outcomes
- Service initialisation now funnels through a single compatibility-aware path, preventing drift between CLI/API call sites.
- Snapshot building logic reads sequentially (FX → commodities → tax) with explicit helper extraction for the trickier tax branching logic.
