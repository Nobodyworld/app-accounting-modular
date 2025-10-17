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
    provider: str = "plugins.tax_oecd_stub.provider",
    s: Session = Depends(get_session),
) -> dict[str, str | int]:
    """Fetch the latest tax rules from an upstream provider."""

    try:
        prov = load_provider(provider)
    except ValueError as exc:  # pragma: no cover - FastAPI integration
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    svc = TaxService(s, prov)
    n = svc.sync_rules()
    return {"synced": n, "provider": prov.name}
