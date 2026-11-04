"""Administrator API (dashboard + operations). Every route except /session requires admin auth."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.accounting import usage
from app.api.deps import admin_token, require_admin
from app.api.v1 import views
from app.auth import keys as key_service
from app.auth.admin import issue_session, token_matches
from app.core.errors import GatewayError
from app.db.base import utcnow
from app.db.models import ApiKey, EvaluationResult, EvaluationRun, Tenant

public = APIRouter(prefix="/admin", tags=["admin"])
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

_SLUG = r"^[a-z0-9][a-z0-9-]{1,62}$"
Money = Annotated[Decimal, Field(ge=0, le=100_000, max_digits=14, decimal_places=8)]


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=512)


class TenantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(pattern=_SLUG)
    name: str = Field(min_length=1, max_length=200)
    rate_limit_rpm: int = Field(default=60, ge=1, le=100_000)
    daily_budget_usd: Money | None = None
    monthly_budget_usd: Money | None = None


class TenantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["active", "suspended"] | None = None
    rate_limit_rpm: int | None = Field(default=None, ge=1, le=100_000)
    daily_budget_usd: Money | None = None
    monthly_budget_usd: Money | None = None
    clear_daily_budget: bool = False
    clear_monthly_budget: bool = False


class KeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="default", min_length=1, max_length=100)


class KeyRotate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grace_s: int = Field(default=0, ge=0, le=7 * 24 * 3600)


# --- session --------------------------------------------------------------------------------


@public.post("/session")
async def create_session(request: Request, body: SessionRequest) -> dict[str, Any]:
    """Exchange the admin token for a short-lived session token (the dashboard keeps only this)."""
    expected = admin_token(request.app.state.settings)
    client = request.client.host if request.client else "unknown"
    if not request.app.state.login_throttle.allow(client):
        raise GatewayError(
            "TOO_MANY_ATTEMPTS",
            "Too many login attempts; wait a minute.",
            status_code=429,
            headers={"Retry-After": "60"},
        )
    if not token_matches(body.token, expected):
        raise GatewayError("UNAUTHORIZED", "Invalid or missing credentials.", status_code=401)
    token, expires = issue_session(expected, request.app.state.settings.admin_session_ttl_s)
    return {"session_token": token, "expires_at": expires}


# --- tenants & keys ----------------------------------------------------------------------


async def _tenant(session: Any, slug: str) -> Tenant:
    tenant: Tenant | None = await session.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is None:
        raise GatewayError("NOT_FOUND", "Tenant not found.", status_code=404)
    return tenant


@router.get("/tenants")
async def list_tenants(request: Request) -> dict[str, Any]:
    async with request.app.state.db.sessionmaker() as session:
        tenants = (await session.scalars(select(Tenant).order_by(Tenant.slug))).all()
        counts = dict(
            (
                await session.execute(
                    select(ApiKey.tenant_id, func.count())
                    .where(ApiKey.revoked_at.is_(None))
                    .group_by(ApiKey.tenant_id)
                )
            ).all()
        )
        items = [
            {**await views.tenant_view(session, t), "unrevoked_keys": counts.get(t.id, 0)}
            for t in tenants
        ]
    return {"items": items}


@router.post("/tenants", status_code=201)
async def create_tenant(request: Request, body: TenantCreate) -> dict[str, Any]:
    async with request.app.state.db.sessionmaker() as session:
        tenant = Tenant(**body.model_dump())
        session.add(tenant)
        try:
            await session.commit()
        except IntegrityError:
            raise GatewayError("CONFLICT", "Tenant slug already exists.", status_code=409) from None
        return await views.tenant_view(session, tenant)


@router.patch("/tenants/{slug}")
async def update_tenant(request: Request, slug: str, body: TenantUpdate) -> dict[str, Any]:
    async with request.app.state.db.sessionmaker() as session:
        tenant = await _tenant(session, slug)
        for field in ("name", "status", "rate_limit_rpm", "daily_budget_usd", "monthly_budget_usd"):
            value = getattr(body, field)
            if value is not None:
                setattr(tenant, field, value)
        if body.clear_daily_budget:
            tenant.daily_budget_usd = None
        if body.clear_monthly_budget:
            tenant.monthly_budget_usd = None
        await session.commit()
        return await views.tenant_view(session, tenant)


@router.get("/tenants/{slug}/keys")
async def list_keys(request: Request, slug: str) -> dict[str, Any]:
    async with request.app.state.db.sessionmaker() as session:
        tenant = await _tenant(session, slug)
        rows = (
            await session.scalars(
                select(ApiKey).where(ApiKey.tenant_id == tenant.id).order_by(ApiKey.created_at)
            )
        ).all()
    return {"tenant": slug, "items": [views.key_view(k) for k in rows]}


@router.post("/tenants/{slug}/keys", status_code=201)
async def create_key(request: Request, slug: str, body: KeyCreate) -> dict[str, Any]:
    pepper = request.app.state.settings.api_key_pepper.get_secret_value()
    async with request.app.state.db.sessionmaker() as session:
        tenant = await _tenant(session, slug)
        issued = await key_service.issue_key(session, tenant, body.name, pepper)
        await session.commit()
        return {
            **views.key_view(issued.key),
            "api_key": issued.plaintext,
            "warning": "Store this key now. It is not stored and can't be shown again.",
        }


async def _key(session: Any, key_id: str) -> tuple[ApiKey, Tenant]:
    try:
        kid = uuid.UUID(key_id)
    except ValueError:
        raise GatewayError("NOT_FOUND", "Key not found.", status_code=404) from None
    row = (
        await session.execute(
            select(ApiKey, Tenant)
            .join(Tenant, Tenant.id == ApiKey.tenant_id)
            .where(ApiKey.id == kid)
        )
    ).first()
    if row is None:
        raise GatewayError("NOT_FOUND", "Key not found.", status_code=404)
    return row[0], row[1]


@router.post("/keys/{key_id}/revoke")
async def revoke_key(request: Request, key_id: str) -> dict[str, Any]:
    async with request.app.state.db.sessionmaker() as session:
        key, _ = await _key(session, key_id)
        await key_service.revoke_key(session, key)
        await session.commit()
        return views.key_view(key)


@router.post("/keys/{key_id}/rotate", status_code=201)
async def rotate_key(request: Request, key_id: str, body: KeyRotate) -> dict[str, Any]:
    pepper = request.app.state.settings.api_key_pepper.get_secret_value()
    async with request.app.state.db.sessionmaker() as session:
        key, tenant = await _key(session, key_id)
        if not key_service.key_is_active(key, utcnow()):
            raise GatewayError("CONFLICT", "Only an active key can be rotated.", status_code=409)
        issued = await key_service.rotate_key(session, key, tenant, pepper, grace_s=body.grace_s)
        await session.commit()
        return {
            "old_key": views.key_view(key),
            "new_key": {**views.key_view(issued.key), "api_key": issued.plaintext},
            "warning": "Store the new key now. It can't be shown again.",
        }


# --- observability -----------------------------------------------------------------------


@router.get("/usage")
async def usage_summary(
    request: Request,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    bucket: Literal["hour", "day"] = "day",
    tenant: str | None = None,
) -> dict[str, Any]:
    since, until = usage.window(days, now=utcnow())
    async with request.app.state.db.sessionmaker() as session:
        tenant_id = (await _tenant(session, tenant)).id if tenant else None
        return await usage.summarize(
            session,
            since=since,
            until=until,
            tenant_id=tenant_id,
            bucket=bucket,
            include_tenants=tenant is None,
        )


@router.get("/requests")
async def list_requests(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=views.MAX_PAGE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    tenant: str | None = None,
    status: str | None = None,
    provider: str | None = None,
    tier: str | None = None,
    fallback: bool | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: Literal[
        "created_at",
        "-created_at",
        "latency_ms",
        "-latency_ms",
        "estimated_list_cost_usd",
        "-estimated_list_cost_usd",
    ] = "-created_at",
) -> dict[str, Any]:
    async with request.app.state.db.sessionmaker() as session:
        tenant_id = (await _tenant(session, tenant)).id if tenant else None
        return await views.list_requests(
            session,
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
            sort=sort,
            status=status,
            provider=provider,
            tier=tier,
            fallback=fallback,
            q=q,
        )


@router.get("/requests/{request_id}")
async def get_request(request: Request, request_id: str) -> dict[str, Any]:
    async with request.app.state.db.sessionmaker() as session:
        return await views.get_request(session, request_id, tenant_id=None)


@router.get("/config")
async def config(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    gateway = request.app.state.gateway
    # Non-secret configuration only. Keys, tokens and URLs with credentials are never included.
    return {
        "environment": settings.app_env,
        "policy": gateway.policy.model_dump(),
        "providers": sorted(gateway.providers),
        "simulated_only": all(p.simulated for p in gateway.providers.values()),
        "settings": {
            "allow_paid_models": settings.allow_paid_models,
            "log_content": settings.log_content,
            "groq_billing_plan": settings.groq_billing_plan,
            "openrouter_free_rpm": settings.openrouter_free_rpm,
            "openrouter_free_rpd": settings.openrouter_free_rpd,
            "request_deadline_s": settings.request_deadline_s,
            "provider_timeout_s": settings.provider_timeout_s,
            "retry_backoff_base_s": settings.retry_backoff_base_s,
            "retry_backoff_cap_s": settings.retry_backoff_cap_s,
            "circuit_failure_threshold": settings.circuit_failure_threshold,
            "circuit_open_s": settings.circuit_open_s,
            "admin_session_ttl_s": settings.admin_session_ttl_s,
            "verify_model_catalog": settings.verify_model_catalog,
        },
    }


# --- evaluation ----------------------------------------------------------------------------


def _run_view(run: EvaluationRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "label": run.label,
        "strategy": run.strategy,
        "dataset_version": run.dataset_version,
        "policy_version": run.policy_version,
        "simulated": run.simulated,
        "status": run.status,
        "preregistration_sha256": run.preregistration_sha256,
        "summary": run.summary,
        "config_snapshot": run.config_snapshot,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


@router.get("/evaluation/runs")
async def evaluation_runs(request: Request) -> dict[str, Any]:
    async with request.app.state.db.sessionmaker() as session:
        runs = (
            await session.scalars(select(EvaluationRun).order_by(EvaluationRun.started_at.desc()))
        ).all()
    return {"items": [_run_view(r) for r in runs]}


@router.get("/evaluation/runs/{run_id}")
async def evaluation_run(request: Request, run_id: str) -> dict[str, Any]:
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise GatewayError("NOT_FOUND", "Run not found.", status_code=404) from None
    async with request.app.state.db.sessionmaker() as session:
        run = await session.get(EvaluationRun, rid)
        if run is None:
            raise GatewayError("NOT_FOUND", "Run not found.", status_code=404)
        results = (
            await session.scalars(select(EvaluationResult).where(EvaluationResult.run_id == rid))
        ).all()
    return {
        **_run_view(run),
        "results": [
            {
                "case_id": str(r.case_id),
                "passed": r.passed,
                "score": r.score,
                "provider": r.provider,
                "model": r.model_id,
                "tier": r.routing_tier,
                "fallback_used": r.fallback_used,
                "error_code": r.error_code,
                "latency_ms": r.latency_ms,
                "estimated_list_cost_usd": str(r.estimated_list_cost_usd)
                if r.estimated_list_cost_usd is not None
                else None,
                "scorer_details": r.scorer_details,
            }
            for r in results
        ],
    }
