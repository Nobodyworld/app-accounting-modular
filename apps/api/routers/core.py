"""Core infrastructure routes."""

from __future__ import annotations

from fastapi import APIRouter

from ..services.plugin_loader import available_plugins

router = APIRouter(tags=["core"])


@router.get("/health")
def health() -> dict[str, str]:
    """Return a basic health indicator."""

    return {"status": "ok"}


@router.get("/providers")
def providers() -> dict[str, list[str]]:
    """List dynamically loadable provider plugins."""

    return {"available": available_plugins()}
