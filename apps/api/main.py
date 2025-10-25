"""FastAPI application factory for the Modular Accounting service."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from apps.observability.logging import RequestContextMiddleware, configure_logging
from apps.observability.metrics import RequestMetricsMiddleware, metrics_registry

from .config import settings
from .db import init_db
from .routers import (
    audit,
    auth,
    core,
    forecast,
    fx,
    health,
    ledger,
    market,
    snapshot,
    reports,
    tax,
    workflow,
)
from .scheduler import shutdown_scheduler, start_scheduler
from .security import get_current_user
from .services.extension_loader import load_configured_extensions
from .services.health import register_default_health_checks

__all__ = ["create_app", "app"]

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""

    configure_logging(
        settings.log_level,
        settings.log_format,
        service_name="modular-accounting-api",
        force=True,
    )
    init_db()
    register_default_health_checks()
    manifests = load_configured_extensions()
    if settings.jwt_secret_is_ephemeral:
        logger.warning(
            "JWT secret is ephemeral and will rotate on process restart. "
            "Set MODACCT_JWT_SECRET_KEY or JWT_SECRET_KEY for persistent sessions."
        )
    if manifests:
        logger.info(
            "Loaded extensions",
            extra={"extensions": [manifest.key for manifest in manifests]},
        )
    # TODO[P2][1d]: Wire structured logging around startup failures for easier triage.

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # pragma: no cover - exercised via tests
        start_scheduler()
        try:
            yield
        finally:
            shutdown_scheduler()

    app = FastAPI(title="Modular Accounting API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RequestMetricsMiddleware, registry=metrics_registry)
    protected = [Depends(get_current_user)]
    router_registry: Iterable[tuple[APIRouter, bool]] = (
        (core.router, False),
        (auth.router, False),
        (audit.router, True),
        (health.router, False),
        (ledger.router, True),
        (fx.router, True),
        (market.router, True),
        (snapshot.router, True),
        (tax.router, True),
        (forecast.router, True),
        (reports.router, True),
        (workflow.router, True),
    )

    for router, requires_auth in router_registry:
        dependencies = protected if requires_auth else None
        app.include_router(router, dependencies=dependencies)

    return app


app = create_app()
