from fastapi import FastAPI
from .db import init_db
from .routers import core, ledger, fx, market, tax, forecast

def create_app():
    init_db()
    app = FastAPI(title="Modular Accounting API", version="0.1.0")
    app.include_router(core.router)
    app.include_router(ledger.router)
    app.include_router(fx.router)
    app.include_router(market.router)
    app.include_router(tax.router)
    app.include_router(forecast.router)
    return app

app = create_app()
