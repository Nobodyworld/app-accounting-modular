"""Core infrastructure routes."""

from __future__ import annotations

from fastapi import APIRouter

from ..services.plugin_loader import available_providers

router = APIRouter(tags=["core"])


@router.get("/health")
def health() -> dict[str, str]:
    """Return a basic health indicator."""

    # TODO - Incorporate database and scheduler checks into health response payload.
    return {"status": "ok"}


@router.get("/providers")
def providers() -> dict[str, list[dict[str, object]]]:
    """List provider plugins exposed via the configuration allowlist."""

    # TODO - Cache provider metadata and include version compatibility info.
    return {"providers": [meta.to_dict() for meta in available_providers()]}
