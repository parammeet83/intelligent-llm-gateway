"""Shared, secret-free serialisers and queries for admin and tenant endpoints."""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting import budget
from app.auth.keys import key_is_active
from app.core.errors import GatewayError
from app.db.base import utcnow
from app.db.models import ApiKey, RequestAttempt, RequestLog, Tenant

MAX_PAGE = 200


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _money(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def key_view(key: ApiKey) -> dict[str, Any]:
    # Prefix only. The hash and plaintext never leave the server.
    return {
        "id": str(key.id),
        "name": key.name,
        "prefix": key.key_prefix,
        "created_at": _iso(key.created_at),
        "last_used_at": _iso(key.last_used_at),
        "revoked_at": _iso(key.revoked_at),
        "expires_at": _iso(key.expires_at),
        "active": key_is_active(key, utcnow()),
    }


async def tenant_view(session: AsyncSession, tenant: Tenant) -> dict[str, Any]:
    periods = await budget.current_periods(session, tenant)
    return {
        "id": str(tenant.id),
        "slug": tenant.slug,
        "name": tenant.name,
        "status": tenant.status,
        "rate_limit_rpm": tenant.rate_limit_rpm,
        "daily_budget_usd": _money(tenant.daily_budget_usd),
        "monthly_budget_usd": _money(tenant.monthly_budget_usd),
        "budget_basis": "estimated list-price cost (shadow budget), not actual charges",
        "budgets": [
            {
                "period": p.period,
                "period_start": p.period_start.isoformat(),
                "limit_usd": str(p.limit_usd),
                "spent_usd": str(p.spent_usd),
                "reserved_usd": str(p.reserved_usd),
                "remaining_usd": str(
                    Decimal(p.limit_usd) - Decimal(p.spent_usd) - Decimal(p.reserved_usd)
                ),
            }
            for p in periods
        ],
        "created_at": _iso(tenant.created_at),
    }


def request_summary(log: RequestLog, tenant_slug: str | None = None) -> dict[str, Any]:
    decision = log.decision or {}
    return {
        "id": str(log.id),
        "tenant": tenant_slug,
        "client_request_id": log.client_request_id or decision.get("client_request_id"),
        "status": log.status,
        "error_code": log.error_code,
        "task_type": log.task_type,
        "prompt_version": log.prompt_version,
        "routing_tier": log.routing_tier,
        "policy_version": log.policy_version,
        "provider": log.selected_provider,
        "model": log.selected_model,
        "attempt_count": log.attempt_count,
        "fallback_used": log.fallback_used,
        "simulated": log.simulated,
        "input_tokens": log.input_tokens,
        "output_tokens": log.output_tokens,
        "latency_ms": log.latency_ms,
        "actual_charge_usd": _money(log.actual_charge_usd),
        "cost_status": log.cost_status,
        "estimated_list_cost_usd": _money(log.estimated_list_cost_usd),
        "list_cost_status": log.list_cost_status,
        "reason_codes": decision.get("reason_codes", []),
        "score": decision.get("score"),
        "created_at": _iso(log.created_at),
        "completed_at": _iso(log.completed_at),
    }


def request_detail(
    log: RequestLog, attempts: list[RequestAttempt], tenant_slug: str | None
) -> dict[str, Any]:
    return {
        **request_summary(log, tenant_slug),
        "prompt_sha256": log.prompt_sha256,
        "input_chars": log.input_chars,
        "decision": log.decision,
        "attempts": [
            {
                "attempt": a.attempt_number,
                "provider": a.provider,
                "model": a.model_id,
                "reason_code": a.reason_code,
                "status": a.status,
                "error_code": a.error_code,
                "http_status": a.http_status,
                "retry_after_s": a.retry_after_s,
                "input_tokens": a.input_tokens,
                "output_tokens": a.output_tokens,
                "latency_ms": a.latency_ms,
                "actual_charge_usd": _money(a.actual_charge_usd),
                "cost_status": a.cost_status,
                "estimated_list_cost_usd": _money(a.estimated_list_cost_usd),
                "list_cost_status": a.list_cost_status,
                "simulated": a.simulated,
                "started_at": _iso(a.started_at),
            }
            for a in attempts
        ],
    }


def filter_requests(
    query: Any,
    *,
    status: str | None,
    provider: str | None,
    tier: str | None,
    fallback: bool | None,
    q: str | None,
) -> Any:
    if status:
        query = query.where(RequestLog.status == status)
    if provider:
        query = query.where(RequestLog.selected_provider == provider)
    if tier:
        query = query.where(RequestLog.routing_tier == tier)
    if fallback is not None:
        query = query.where(RequestLog.fallback_used.is_(fallback))
    if q:
        term = q.strip()
        clauses = [RequestLog.client_request_id == term, RequestLog.selected_model == term]
        with contextlib.suppress(ValueError):
            clauses.append(RequestLog.id == uuid.UUID(term))
        query = query.where(or_(*clauses))
    return query


async def list_requests(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None,
    limit: int,
    offset: int,
    sort: str = "-created_at",
    **filters: Any,
) -> dict[str, Any]:
    base = select(RequestLog, Tenant.slug).join(Tenant, Tenant.id == RequestLog.tenant_id)
    if tenant_id is not None:
        base = base.where(RequestLog.tenant_id == tenant_id)
    base = filter_requests(base, **filters)
    total = int(
        await session.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    )
    column = {
        "created_at": RequestLog.created_at,
        "latency_ms": RequestLog.latency_ms,
        "estimated_list_cost_usd": RequestLog.estimated_list_cost_usd,
    }.get(sort.lstrip("-"), RequestLog.created_at)
    ordered = base.order_by(column.desc() if sort.startswith("-") else column.asc(), RequestLog.id)
    rows = (await session.execute(ordered.limit(min(limit, MAX_PAGE)).offset(offset))).all()
    return {
        "total": total,
        "limit": min(limit, MAX_PAGE),
        "offset": offset,
        "items": [request_summary(log, slug) for log, slug in rows],
    }


async def get_request(
    session: AsyncSession, request_id: str, *, tenant_id: uuid.UUID | None
) -> dict[str, Any]:
    try:
        rid = uuid.UUID(request_id)
    except ValueError:
        raise GatewayError("NOT_FOUND", "Request not found.", status_code=404) from None
    query = (
        select(RequestLog, Tenant.slug)
        .join(Tenant, Tenant.id == RequestLog.tenant_id)
        .where(RequestLog.id == rid)
    )
    if tenant_id is not None:
        # A tenant can't see (or confirm the existence of) another tenant's request.
        query = query.where(RequestLog.tenant_id == tenant_id)
    row = (await session.execute(query)).first()
    if row is None:
        raise GatewayError("NOT_FOUND", "Request not found.", status_code=404)
    log: RequestLog = row[0]
    slug: str = row[1]
    attempts = (
        await session.scalars(
            select(RequestAttempt)
            .where(RequestAttempt.request_id == log.id)
            .order_by(RequestAttempt.attempt_number)
        )
    ).all()
    return request_detail(log, list(attempts), slug)
