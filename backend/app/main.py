from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.v1 import admin as admin_api
from app.api.v1.catalog import router as catalog_router
from app.api.v1.generate import router as generate_router
from app.api.v1.health import router as health_router
from app.api.v1.tenant import router as tenant_router
from app.auth.admin import LoginThrottle
from app.core.config import Settings, get_settings
from app.core.errors import error_body, install_error_handlers
from app.core.logging import configure_logging
from app.db.session import Database
from app.providers.base import Provider
from app.providers.registry import build_providers, refresh_catalogs
from app.services.factory import build_gateway

REQUEST_ID_HEADER = "X-Request-ID"
MAX_BODY_BYTES = 512 * 1024
_CATALOG_REFRESH_TIMEOUT_S = 15.0

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None, *, providers: dict[str, Provider] | None = None
) -> FastAPI:
    """`providers` lets tests inject adapters wired to fake transports."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, log_content=settings.log_content)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active = providers if providers is not None else build_providers(settings)
        app.state.settings = settings
        app.state.login_throttle = LoginThrottle(limit=settings.admin_login_attempts_per_min)
        app.state.db = Database(settings.database_url.get_secret_value(), echo=settings.db_echo)
        app.state.providers = active
        app.state.gateway = build_gateway(settings, app.state.db, active)
        if settings.verify_model_catalog:
            try:
                await asyncio.wait_for(
                    refresh_catalogs(active, app.state.gateway.health),
                    timeout=_CATALOG_REFRESH_TIMEOUT_S,
                )
            except TimeoutError:
                logger.warning("model_catalog_refresh_timed_out")
        try:
            yield
        finally:
            for provider in active.values():
                await provider.aclose()
            await app.state.db.dispose()

    app = FastAPI(
        title="RouteWise AI Gateway",
        version=__version__,
        lifespan=lifespan,
        # Interactive docs are handy locally but expose the full surface; off in production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Server-generated trace ID (also the request_logs primary key). Client-supplied
        # idempotency keys are a separate field.
        request.state.request_id = str(uuid.uuid4())
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            response: Response = JSONResponse(
                status_code=413,
                content=error_body(
                    "PAYLOAD_TOO_LARGE",
                    f"Request body exceeds {MAX_BODY_BYTES} bytes.",
                    request.state.request_id,
                ),
            )
        else:
            response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        return response

    install_error_handlers(app)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(catalog_router, prefix="/api/v1")
    app.include_router(generate_router, prefix="/api/v1")
    app.include_router(tenant_router, prefix="/api/v1")
    app.include_router(admin_api.public, prefix="/api/v1")
    app.include_router(admin_api.router, prefix="/api/v1")
    return app
