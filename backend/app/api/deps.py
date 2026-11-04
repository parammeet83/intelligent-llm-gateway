"""Authentication dependencies.

Tenants:  `Authorization: Bearer rw_<id>_<secret>` (tenant API key). The tenant is always derived
          from the key, never from the request body or a header the client chooses.
Admins:   `Authorization: Bearer <ADMIN_TOKEN>` or a dashboard session token (`rws_...`).

Every failure returns the same generic message, so callers can't probe which keys exist.
"""

from __future__ import annotations

from fastapi import Request

from app.auth.admin import token_matches, verify_session
from app.auth.keys import AuthenticatedTenant, authenticate
from app.core.config import Settings
from app.core.errors import GatewayError


def _bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    return header[7:].strip() if header[:7].lower() == "bearer " else ""


def _unauthorized() -> GatewayError:
    return GatewayError("UNAUTHORIZED", "Invalid or missing credentials.", status_code=401)


async def require_tenant(request: Request) -> AuthenticatedTenant:
    presented = _bearer(request)
    if not presented:
        raise _unauthorized()
    settings: Settings = request.app.state.settings
    async with request.app.state.db.sessionmaker() as session:
        auth = await authenticate(
            session,
            presented,
            settings.api_key_pepper.get_secret_value(),
            touch_interval_s=settings.api_key_touch_interval_s,
        )
    if auth is None:
        raise _unauthorized()
    request.state.tenant_id = str(auth.tenant.id)
    return auth


def admin_token(settings: Settings) -> str:
    token = settings.admin_token.get_secret_value() if settings.admin_token else ""
    if not token:
        raise GatewayError(
            "ADMIN_NOT_CONFIGURED",
            "Administration is disabled until ADMIN_TOKEN is configured on the server.",
            status_code=401,
        )
    return token


async def require_admin(request: Request) -> None:
    expected = admin_token(request.app.state.settings)
    presented = _bearer(request)
    if not presented:
        raise _unauthorized()
    if not (verify_session(presented, expected) or token_matches(presented, expected)):
        raise _unauthorized()
