"""Core infrastructure routes."""

from __future__ import annotations

from fastapi import APIRouter

from ..services.plugin_loader import available_providers

router = APIRouter(tags=["core"])


@router.get("/health")
def health() -> dict[str, str]:
    """Return a basic health indicator."""

    return {"status": "ok"}


@router.get("/providers")
def providers() -> dict[str, list[dict[str, object]]]:
    """List provider plugins exposed via the configuration allowlist."""

    return {"providers": [meta.to_dict() for meta in available_providers()]}
