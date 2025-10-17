"""Tax rule synchronisation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..services.plugin_loader import load_provider
from ..services.tax_service import TaxService

router = APIRouter(prefix="/tax", tags=["tax"])


@router.post("/sync")
def sync_tax(
    provider_key: str = "tax:oecd_stub",
    s: Session = Depends(get_session),
) -> dict[str, str | int]:
    """Fetch the latest tax rules from an upstream provider."""

    try:
        handle = load_provider(provider_key)
    except ValueError as exc:  # pragma: no cover - FastAPI integration
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    svc = TaxService(s, handle.instance)
    n = svc.sync_rules()
    return {
        "synced": n,
        "provider": handle.metadata.name,
        "provider_key": handle.metadata.key,
    }
