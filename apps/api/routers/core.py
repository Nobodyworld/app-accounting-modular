from fastapi import APIRouter

from ..services.plugin_loader import available_plugins

router = APIRouter()

@router.get("/health")
def health() -> dict[str, str]:
    """Health probe used by monitoring and orchestration."""

    return {"status": "ok"}

@router.get("/providers")
def providers() -> dict[str, list[str]]:
    """Expose dynamically discoverable data providers."""

    return {"available": available_plugins()}
