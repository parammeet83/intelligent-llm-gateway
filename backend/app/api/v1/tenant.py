"""Tenant self-service: everything is scoped to the tenant that owns the presented API key."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.accounting import usage
from app.api.deps import require_tenant
from app.api.v1 import views
from app.auth.keys import AuthenticatedTenant
from app.db.base import utcnow

router = APIRouter(prefix="/me", tags=["tenant"])
Tenant = Annotated[AuthenticatedTenant, Depends(require_tenant)]


@router.get("")
async def me(request: Request, auth: Tenant) -> dict[str, Any]:
    async with request.app.state.db.sessionmaker() as session:
        view = await views.tenant_view(session, auth.tenant)
    return {**view, "api_key_prefix": auth.key_prefix}


@router.get("/usage")
async def my_usage(
    request: Request,
    auth: Tenant,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    bucket: Literal["hour", "day"] = "day",
) -> dict[str, Any]:
    since, until = usage.window(days, now=utcnow())
    async with request.app.state.db.sessionmaker() as session:
        return await usage.summarize(
            session, since=since, until=until, tenant_id=auth.tenant.id, bucket=bucket
        )


@router.get("/requests")
async def my_requests(
    request: Request,
    auth: Tenant,
    limit: Annotated[int, Query(ge=1, le=views.MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: str | None = None,
) -> dict[str, Any]:
    async with request.app.state.db.sessionmaker() as session:
        return await views.list_requests(
            session,
            tenant_id=auth.tenant.id,
            limit=limit,
            offset=offset,
            status=status,
            provider=None,
            tier=None,
            fallback=None,
            q=None,
        )


@router.get("/requests/{request_id}")
async def my_request(request: Request, auth: Tenant, request_id: str) -> dict[str, Any]:
    async with request.app.state.db.sessionmaker() as session:
        return await views.get_request(session, request_id, tenant_id=auth.tenant.id)
