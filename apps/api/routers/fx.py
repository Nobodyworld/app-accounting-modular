"""Foreign-exchange related routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..services.fx_service import FXService
from ..services.plugin_loader import load_provider

router = APIRouter(prefix="/fx", tags=["fx"])


@router.post("/sync")
def sync_fx(
    base: str = "USD",
    provider: str = "plugins.fx_ecb.provider",
    s: Session = Depends(get_session),
) -> dict[str, str | int]:
    """Synchronise the latest FX rates from the configured provider."""

    try:
        prov = load_provider(provider)
    except ValueError as exc:  # pragma: no cover - FastAPI integration
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    svc = FXService(s, prov)
    count = svc.sync(base=base)
    return {"synced": count, "provider": prov.name, "base": base}
