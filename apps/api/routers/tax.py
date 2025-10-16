from fastapi import APIRouter, Depends
from sqlmodel import Session
from ..db import get_session
from ..services.tax_service import TaxService
from ..services.plugin_loader import load_provider

router = APIRouter(prefix="/tax", tags=["tax"])

@router.post("/sync")
def sync_tax(provider: str = "plugins.tax_oecd_stub.provider", s: Session = Depends(get_session)):
    prov = load_provider(provider)
    svc = TaxService(s, prov)
    n = svc.sync_rules()
    return {"synced": n, "provider": prov.name}
