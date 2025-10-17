"""FastAPI application factory for the Modular Accounting service."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from .db import init_db
from .routers import auth, core, forecast, fx, ledger, market, tax
from .security import get_current_user

__all__ = ["create_app", "app"]


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""

    init_db()
    app = FastAPI(title="Modular Accounting API", version="0.1.0")
    protected = [Depends(get_current_user)]
    app.include_router(core.router)
    app.include_router(auth.router)
    app.include_router(ledger.router, dependencies=protected)
    app.include_router(fx.router, dependencies=protected)
    app.include_router(market.router, dependencies=protected)
    app.include_router(tax.router, dependencies=protected)
    app.include_router(forecast.router, dependencies=protected)
    return app


app = create_app()
