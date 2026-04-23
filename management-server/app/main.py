"""FastAPI app factory.

Wires routers, middleware (auth → security), health check, and the
OpenAPI schema. Nothing app-specific lives here — every concern has its
own module.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app import __version__
from app.auth import AuthMiddleware
from app.config import get_settings
from app.routers import agents, auth, commands, customers, stubs
from app.security import CSPMiddleware, CSRFMiddleware, RateLimitMiddleware

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log.info(
        "sawyer-mgmt starting: version=%s env=%s log_level=%s",
        __version__,
        settings.environment,
        settings.log_level,
    )
    yield
    log.info("sawyer-mgmt shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="sawyer-cloud management server",
        version=__version__,
        lifespan=lifespan,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Middleware order is bottom-up (last added runs first on the response
    # path). We want CSP headers on every response, rate-limit observed
    # count on every response, CSRF check after auth resolves principal,
    # auth resolves credentials before everything else.
    app.add_middleware(CSPMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(AuthMiddleware)

    # Health + root.
    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    # /api/v1 is the stable public surface.
    api_v1_routers = (
        auth.router,
        customers.router,
        agents.router,
        commands.router,
        stubs.features,
        stubs.images,
        stubs.audits,
        stubs.break_glass,
        stubs.per_customer_stubs,
    )
    for r in api_v1_routers:
        app.include_router(r, prefix="/api/v1")

    return app


app = create_app()
