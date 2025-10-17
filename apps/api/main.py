"""FastAPI application factory for the Modular Accounting service."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from .db import init_db
from .routers import audit, auth, core, forecast, fx, ledger, market, reports, tax, workflow
from .scheduler import shutdown_scheduler, start_scheduler
from .security import get_current_user

__all__ = ["create_app", "app"]


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""

    init_db()
    app = FastAPI(title="Modular Accounting API", version="0.1.0")
    protected = [Depends(get_current_user)]
    app.include_router(core.router)
    app.include_router(auth.router)
    app.include_router(audit.router, dependencies=protected)
    app.include_router(ledger.router, dependencies=protected)
    app.include_router(fx.router, dependencies=protected)
    app.include_router(market.router, dependencies=protected)
    app.include_router(tax.router, dependencies=protected)
    app.include_router(forecast.router, dependencies=protected)
    app.include_router(reports.router, dependencies=protected)
    app.include_router(workflow.router, dependencies=protected)
    @app.on_event("startup")
    def _start_scheduler() -> None:  # pragma: no cover - framework hook
        start_scheduler()

    @app.on_event("shutdown")
    def _stop_scheduler() -> None:  # pragma: no cover - framework hook
        shutdown_scheduler()

    return app


app = create_app()
