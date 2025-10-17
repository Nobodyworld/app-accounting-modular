"""FastAPI application factory for the Modular Accounting service."""

from __future__ import annotations

from fastapi import FastAPI

from .db import init_db
from .routers import audit, core, forecast, fx, ledger, market, tax

__all__ = ["create_app", "app"]


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""

    init_db()
    app = FastAPI(title="Modular Accounting API", version="0.1.0")
    app.include_router(core.router)
    app.include_router(audit.router)
    app.include_router(ledger.router)
    app.include_router(fx.router)
    app.include_router(market.router)
    app.include_router(tax.router)
    app.include_router(forecast.router)
    return app


app = create_app()
