from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..db import get_session
from ..services.plugin_loader import load_provider
from ..services.tax_service import TaxService

router = APIRouter(prefix="/tax", tags=["tax"])

@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_tax(
    provider: str = "plugins.tax_oecd_stub.provider",
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        provider_impl = load_provider(provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    service = TaxService(session, provider_impl)
    count = service.sync_rules()
    return {"synced": count, "provider": provider_impl.name}
