"""Extension-focused API routes for discovery and automation."""

from __future__ import annotations

from fastapi import APIRouter

from apps.api.schemas import ExtensionContractSchema
from apps.api.services.extension_loader import (
    load_configured_extensions,
    registered_contracts,
)

router = APIRouter(prefix="/extensions", tags=["Extensions"])


@router.get("/contracts", response_model=list[ExtensionContractSchema])
def list_contracts() -> list[ExtensionContractSchema]:
    """Return registered extension contracts with extension metadata."""

    load_configured_extensions()
    payload: list[ExtensionContractSchema] = []
    for status, contract in registered_contracts():
        payload.append(ExtensionContractSchema.from_status(status, contract))
    return payload
