"""Liveness and readiness probes.

/health  - the process is up. No dependencies touched; safe for frequent polling.
/ready   - the database is reachable and its schema is at the expected Alembic revision.
Neither endpoint reveals connection details, hostnames, or error text from the driver.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.db.migrations import expected_head

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    providers = request.app.state.providers
    return {
        "status": "ok",
        "version": __version__,
        "environment": request.app.state.settings.app_env,
        "providers": sorted(providers),
        # True when every enabled provider is the mock: the dashboard shows a DEMO banner.
        "simulated_only": all(p.simulated for p in providers.values()),
    }


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        async with request.app.state.db.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
            row = (await conn.execute(text("SELECT version_num FROM alembic_version"))).first()
            current = row[0] if row else None
            checks["migrations"] = "ok" if current == expected_head() else "pending"
    except Exception as exc:
        logger.warning("readiness_check_failed", extra={"error_type": type(exc).__name__})
        checks.setdefault("database", "unavailable")
        checks.setdefault("migrations", "unknown")

    ok = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ready" if ok else "not_ready", "checks": checks},
    )
