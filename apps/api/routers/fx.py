from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..db import get_session
from ..services.fx_service import FXService
from ..services.plugin_loader import load_provider

router = APIRouter(prefix="/fx", tags=["fx"])

@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_fx(
    base: str = "USD",
    provider: str = "plugins.fx_ecb.provider",
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        provider_impl = load_provider(provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    service = FXService(session, provider_impl)
    try:
        count = service.sync(base=base)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {"synced": count, "provider": provider_impl.name}
