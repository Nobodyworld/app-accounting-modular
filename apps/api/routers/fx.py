from fastapi import APIRouter, Depends, Query, HTTPException
from sqlmodel import Session
from ..db import get_session
from ..services.fx_service import FXService
from ..services.plugin_loader import load_provider

router = APIRouter(prefix="/fx", tags=["fx"])

@router.post("/sync")
def sync_fx(base: str = "USD", provider: str = "plugins.fx_ecb.provider", s: Session = Depends(get_session)):
    prov = load_provider(provider)
    svc = FXService(s, prov)
    count = svc.sync(base=base)
    return {"synced": count, "provider": prov.name}
