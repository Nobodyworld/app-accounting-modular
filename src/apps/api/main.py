"""FastAPI application factory for the Modular Accounting service."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from apps.observability import RequestTraceMiddleware, configure_tracing
from apps.observability.logging import RequestContextMiddleware, configure_logging
from apps.observability.metrics import RequestMetricsMiddleware, metrics_registry

from .config import settings
from .db import init_db
from .routers import (
    audit,
    auth,
    core,
    extensions,
    forecast,
    fx,
    health,
    ledger,
    market,
    reports,
    snapshot,
    tax,
    workflow,
)
from .scheduler import shutdown_scheduler, start_scheduler
from .security import get_current_user
from .services.extension_loader import load_configured_extensions
from .services.health import register_default_health_checks
from .startup import StartupContext, StartupManager, StartupStep
from .version import API_VERSION

__all__ = ["create_app", "app"]

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""

    startup_manager = StartupManager(logger=logging.getLogger("apps.api.startup"))
    startup_context: StartupContext = {}

    def _configure_logging(_: StartupContext) -> None:
        configure_logging(
            settings.log_level,
            settings.log_format,
            service_name="modular-accounting-api",
            force=True,
        )

    def _configure_tracing(_: StartupContext) -> None:
        configure_tracing(
            service_name="modular-accounting-api",
            exporter=settings.tracing_exporter,
            endpoint=settings.tracing_otlp_endpoint,
        )

    def _initialise_database(_: StartupContext) -> None:
        init_db()

    def _register_health(_: StartupContext) -> None:
        register_default_health_checks()

    def _load_extensions(context: StartupContext) -> None:
        manifests = load_configured_extensions()
        context["extensions"] = tuple(manifests)
        if manifests:
            logger.info(
                "Loaded extensions",
                extra={"extensions": [manifest.key for manifest in manifests]},
            )

    def _warn_ephemeral_secret(_: StartupContext) -> None:
        if settings.jwt_secret_is_ephemeral:
            logger.warning(
                "JWT secret is ephemeral and will rotate on process restart. "
                "Set MODACCT_JWT_SECRET_KEY or JWT_SECRET_KEY for persistent sessions."
            )

    startup_steps = (
        StartupStep(name="configure_logging", action=_configure_logging),
        StartupStep(name="configure_tracing", action=_configure_tracing),
        StartupStep(name="initialise_database", action=_initialise_database),
        StartupStep(name="register_health_checks", action=_register_health),
        StartupStep(name="load_extensions", action=_load_extensions),
        StartupStep(name="warn_ephemeral_secret", action=_warn_ephemeral_secret, fatal=False),
    )

    startup_records = startup_manager.run(startup_steps, context=startup_context)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # pragma: no cover - exercised via tests
        start_scheduler()
        try:
            yield
        finally:
            shutdown_scheduler()

    app = FastAPI(title="Modular Accounting API", version=API_VERSION, lifespan=lifespan)
    app.add_middleware(RequestTraceMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RequestMetricsMiddleware, registry=metrics_registry)
    app.state.startup_records = startup_records
    app.state.extension_manifests = startup_context.get("extensions", ())
    protected = [Depends(get_current_user)]
    router_registry: Iterable[tuple[APIRouter, bool]] = (
        (core.router, False),
        (auth.router, False),
        (audit.router, True),
        (health.router, False),
        (extensions.router, False),
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
