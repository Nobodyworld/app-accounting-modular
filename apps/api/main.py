"""FastAPI application factory for the Modular Accounting service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Iterable, Tuple

from fastapi import APIRouter, Depends, FastAPI

from .config import settings
from .db import init_db
from .routers import audit, auth, core, forecast, fx, ledger, market, reports, tax, workflow
from .scheduler import shutdown_scheduler, start_scheduler
from .security import get_current_user

__all__ = ["create_app", "app"]

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""

    init_db()
    if settings.jwt_secret_is_ephemeral:
        logger.warning(
            "JWT secret is ephemeral and will rotate on process restart. "
            "Set MODACCT_JWT_SECRET_KEY or JWT_SECRET_KEY for persistent sessions."
        )
    # TODO - Wire structured logging around startup failures for easier triage.

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # pragma: no cover - exercised via tests
        start_scheduler()
        try:
            yield
        finally:
            shutdown_scheduler()

    app = FastAPI(title="Modular Accounting API", version="0.1.0", lifespan=lifespan)
    protected = [Depends(get_current_user)]
    router_registry: Iterable[Tuple[APIRouter, bool]] = (
        (core.router, False),
        (auth.router, False),
        (audit.router, True),
        (ledger.router, True),
        (fx.router, True),
        (market.router, True),
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
