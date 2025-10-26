"""Routes exposing consolidated data snapshots."""

from __future__ import annotations

from typing import Sequence

from fastapi import APIRouter, Depends, Query

from ..schemas import (
    ScenarioBatchRequest,
    ScenarioBatchResponse,
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
