# Scenario Plan API Contract

Scenario plans and direct scenario batches intentionally use different request contracts.

## Plan preview

`POST /snapshot/plans/preview` accepts a plan with shared `defaults` and one or more scenario entries. The endpoint is part of the authenticated snapshot router.

Fields supported by plan defaults are:

- `base_currency`
- `commodity_symbols`
- `jurisdictions`
- `tags`

A scenario may omit those fields when the plan supplies the required value. Defaults are merged first, and scenario-specific values then override them before the strict domain `SnapshotScenario` is constructed.

Omission and explicit `null` are distinct. An omitted field inherits its plan default. An explicitly supplied `null` remains an override where the domain model permits it, such as clearing a default jurisdiction scope.

The checked-in [`examples/scenario-plan.json`](examples/scenario-plan.json) demonstrates a default USD base currency and a scenario-specific EUR override.

## Direct batch execution

`POST /snapshot/scenarios` does not accept plan defaults. Each scenario continues to use the strict `ScenarioDefinition` contract and must provide its own `base_currency`.

This separation prevents the plan-preview schema from weakening direct batch validation.
