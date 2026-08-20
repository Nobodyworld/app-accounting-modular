"""Routes exposing consolidated data snapshots."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from apps.modular_accounting.application import ScenarioPlanValidationError

from ..dependencies import session_with_audit_context
from ..models.models import User
from ..schemas import (
    ScenarioBatchRequest,
    ScenarioBatchResponse,
    ScenarioPlanPayload,
    ScenarioPlanPreviewResponse,
    SnapshotResponse,
)
from ..security import get_current_organization, get_current_user
from ..services.provider_governance_service import ProviderGovernanceError, ProviderGovernanceService
from ..services.snapshot_service import SnapshotOrchestrator

router = APIRouter(prefix="/snapshot", tags=["snapshot"])


def get_snapshot_orchestrator_factory() -> Callable[..., SnapshotOrchestrator]:
    """Return a construction seam invoked only after tenant authorization."""

    return SnapshotOrchestrator


def _governed_orchestrator(
    organization_id: int,
    session: Session,
    current_user: User,
    *,
    fx_provider_key: str | None = None,
    commodity_provider_key: str | None = None,
    tax_provider_key: str | None = None,
    factory: Callable[..., SnapshotOrchestrator] = SnapshotOrchestrator,
) -> SnapshotOrchestrator:
    context = get_current_organization(organization_id, session, current_user)
    if current_user.id is None or context.organization.id is None:
        raise HTTPException(status_code=500, detail="Organization context unavailable")
    governance = ProviderGovernanceService(session, context.organization.id, current_user.id)
    try:
        return factory(
            fx_provider_key=fx_provider_key,
            commodity_provider_key=commodity_provider_key,
            tax_provider_key=tax_provider_key,
            provider_resolver=governance.resolve_provider,
        )
    except ProviderGovernanceError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc


# agent-entrypoint: HTTP surface for automated snapshot orchestration.
@router.get("", response_model=SnapshotResponse)
def fetch_snapshot(
    organization_id: int = Query(..., ge=1),
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
    fx_provider_key: str | None = Query(default=None, min_length=1, max_length=96),
    commodity_provider_key: str | None = Query(default=None, min_length=1, max_length=96),
    tax_provider_key: str | None = Query(default=None, min_length=1, max_length=96),
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
    orchestrator_factory: Callable[..., SnapshotOrchestrator] = Depends(get_snapshot_orchestrator_factory),
) -> SnapshotResponse:
    """Return a consolidated snapshot across FX, commodities, and tax data.

    The response now includes diagnostics describing the breadth and recency of
    the underlying adapter data so clients can make freshness decisions without
    recomputing aggregates locally.
    """

    orchestrator = _governed_orchestrator(
        organization_id,
        session,
        current_user,
        fx_provider_key=fx_provider_key,
        commodity_provider_key=commodity_provider_key,
        tax_provider_key=tax_provider_key,
        factory=orchestrator_factory,
    )
    result = orchestrator.build_snapshot(
        base_currency=base,
        commodity_symbols=commodity,
        jurisdictions=jurisdiction,
    )
    return SnapshotResponse.from_result(result)


@router.post("/scenarios", response_model=ScenarioBatchResponse)
def fetch_snapshot_scenarios(
    payload: ScenarioBatchRequest,
    organization_id: int = Query(..., ge=1),
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
    orchestrator_factory: Callable[..., SnapshotOrchestrator] = Depends(get_snapshot_orchestrator_factory),
) -> ScenarioBatchResponse:
    """Execute multiple snapshot scenarios and return aggregate diagnostics."""

    orchestrator = _governed_orchestrator(
        organization_id,
        session,
        current_user,
        factory=orchestrator_factory,
    )
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
