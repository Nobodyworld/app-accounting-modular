"""Routes exposing consolidated data snapshots."""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.modular_accounting.application import ScenarioPlanValidationError

from ..schemas import (
    ScenarioBatchRequest,
    ScenarioBatchResponse,
    ScenarioPlanPayload,
    ScenarioPlanPreviewResponse,
    SnapshotResponse,
)
from ..services.snapshot_service import SnapshotOrchestrator

router = APIRouter(prefix="/snapshot", tags=["snapshot"])


def get_snapshot_orchestrator() -> SnapshotOrchestrator:
    """Return the default snapshot orchestrator."""

    return SnapshotOrchestrator()


# agent-entrypoint: HTTP surface for automated snapshot orchestration.
@router.get("", response_model=SnapshotResponse)
def fetch_snapshot(
    base: str = Query(
        "USD",
        description="Base currency used when requesting FX rates.",
        alias="base",
    ),
    commodity: Sequence[str] | None = Query(
        default=None,
        description="Commodity symbols to include in the snapshot.",
        alias="commodity",
    ),
    jurisdiction: Sequence[str] | None = Query(
        default=None,
        description="Jurisdictions used to filter tax rules.",
        alias="jurisdiction",
    ),
    orchestrator: SnapshotOrchestrator = Depends(get_snapshot_orchestrator),
) -> SnapshotResponse:
    """Return a consolidated snapshot across FX, commodities, and tax data.

    The response now includes diagnostics describing the breadth and recency of
    the underlying adapter data so clients can make freshness decisions without
    recomputing aggregates locally.
    """

    result = orchestrator.build_snapshot(
        base_currency=base,
        commodity_symbols=commodity,
        jurisdictions=jurisdiction,
    )
    return SnapshotResponse.from_result(result)


@router.post("/scenarios", response_model=ScenarioBatchResponse)
def fetch_snapshot_scenarios(
    payload: ScenarioBatchRequest,
    orchestrator: SnapshotOrchestrator = Depends(get_snapshot_orchestrator),
) -> ScenarioBatchResponse:
    """Execute multiple snapshot scenarios and return aggregate diagnostics."""

    batch = orchestrator.run_scenarios(
        payload.to_scenarios(),
        reset_cache_between_runs=payload.reset_cache_between_runs,
    )
    return ScenarioBatchResponse.from_batch(batch)


@router.post("/plans/preview", response_model=ScenarioPlanPreviewResponse)
def preview_scenario_plan(payload: ScenarioPlanPayload) -> ScenarioPlanPreviewResponse:
    """Validate a scenario plan and return a metadata summary."""

    try:
        plan = payload.to_plan()
    except ScenarioPlanValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    summary = plan.summary()
    return ScenarioPlanPreviewResponse.from_plan(plan, summary)
