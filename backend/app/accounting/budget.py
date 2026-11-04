"""Tenant shadow budgets (daily + monthly), enforced on estimated list-price cost.

Concurrency: a reservation is one conditional UPDATE per period:

    UPDATE tenant_budgets SET reserved_usd = reserved_usd + :amount
    WHERE tenant_id = :t AND period = :p AND period_start = :s
      AND spent_usd + reserved_usd + :amount <= limit_usd

PostgreSQL takes a row lock and re-checks the WHERE clause against the latest committed row
(READ COMMITTED), so N concurrent requests can never jointly reserve more than the limit. SQLite
serialises writers. Daily and monthly are reserved in one transaction: both succeed or neither.

Lifecycle: reserve(worst case) -> execute -> settle(actual estimated cost) which moves the
consumed amount into `spent_usd` and releases the whole reservation. A crash in between leaves
`request_logs.budget_reservation` on a pending row; `release_stale` settles it, charging the
full hold.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, case, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models import RequestLog, Tenant, TenantBudgetPeriod

_PLACES = Decimal("0.00000001")


class BudgetExhausted(Exception):
    def __init__(self, period: str) -> None:
        super().__init__(f"{period} budget exhausted")
        self.period = period


def period_starts(now: datetime) -> dict[str, date]:
    day = now.date()
    return {"daily": day, "monthly": day.replace(day=1)}


def configured_limits(tenant: Tenant, now: datetime) -> list[tuple[str, date, Decimal]]:
    starts = period_starts(now)
    limits = []
    if tenant.daily_budget_usd is not None:
        limits.append(("daily", starts["daily"], Decimal(tenant.daily_budget_usd)))
    if tenant.monthly_budget_usd is not None:
        limits.append(("monthly", starts["monthly"], Decimal(tenant.monthly_budget_usd)))
    return limits


async def _ensure_rows(
    session: AsyncSession, tenant_id: uuid.UUID, limits: list[tuple[str, date, Decimal]]
) -> None:
    dialect = session.bind.dialect.name if session.bind else "sqlite"
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
    for period, start, limit in limits:
        await session.execute(
            insert(TenantBudgetPeriod)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                period=period,
                period_start=start,
                limit_usd=limit,
                spent_usd=Decimal(0),
                reserved_usd=Decimal(0),
                updated_at=utcnow(),
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "period", "period_start"])
        )
        # A limit changed by an admin applies to the current period immediately.
        await session.execute(
            update(TenantBudgetPeriod)
            .where(
                TenantBudgetPeriod.tenant_id == tenant_id,
                TenantBudgetPeriod.period == period,
                TenantBudgetPeriod.period_start == start,
                TenantBudgetPeriod.limit_usd != limit,
            )
            .values(limit_usd=limit)
            .execution_options(synchronize_session=False)
        )


async def current_periods(
    session: AsyncSession, tenant: Tenant, *, now: datetime | None = None
) -> list[TenantBudgetPeriod]:
    limits = configured_limits(tenant, now or utcnow())
    if not limits:
        return []
    await _ensure_rows(session, tenant.id, limits)
    await session.commit()
    rows = (
        await session.scalars(
            select(TenantBudgetPeriod).where(
                TenantBudgetPeriod.tenant_id == tenant.id,
                TenantBudgetPeriod.period_start.in_({start for _, start, _ in limits}),
                TenantBudgetPeriod.period.in_({p for p, _, _ in limits}),
            )
        )
    ).all()
    wanted = {(p, s) for p, s, _ in limits}
    return [r for r in rows if (r.period, r.period_start) in wanted]


async def remaining(
    session: AsyncSession, tenant: Tenant, *, now: datetime | None = None
) -> Decimal | None:
    """Smallest headroom across configured periods; None if the tenant has no budget."""
    periods = await current_periods(session, tenant, now=now)
    if not periods:
        return None
    return min(
        Decimal(p.limit_usd) - Decimal(p.spent_usd) - Decimal(p.reserved_usd) for p in periods
    )


async def reserve(
    session: AsyncSession,
    tenant: Tenant,
    amount: Decimal,
    *,
    now: datetime | None = None,
    commit: bool = True,
) -> list[dict[str, Any]]:
    """Atomically reserve `amount` in every configured period, or raise BudgetExhausted.
    With commit=False the caller commits (e.g. together with the request row)."""
    limits = configured_limits(tenant, now or utcnow())
    if not limits:
        return []
    amount = amount.quantize(_PLACES)
    tenant_id = tenant.id
    await _ensure_rows(session, tenant_id, limits)
    reservation: list[dict[str, Any]] = []
    # SAVEPOINT: if a later period fails, only this reservation is undone; the caller's other
    # pending changes and loaded objects are left alone.
    async with session.begin_nested():
        for period, start, _ in limits:
            result = await session.execute(
                update(TenantBudgetPeriod)
                .where(
                    TenantBudgetPeriod.tenant_id == tenant_id,
                    TenantBudgetPeriod.period == period,
                    TenantBudgetPeriod.period_start == start,
                    TenantBudgetPeriod.spent_usd + TenantBudgetPeriod.reserved_usd + amount
                    <= TenantBudgetPeriod.limit_usd,
                )
                .values(reserved_usd=TenantBudgetPeriod.reserved_usd + amount, updated_at=utcnow())
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:  # type: ignore[attr-defined]
                raise BudgetExhausted(period)
            reservation.append(
                {"period": period, "period_start": start.isoformat(), "amount": str(amount)}
            )
    if commit:
        await session.commit()
    return reservation


async def settle(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    reservation: list[dict[str, Any]],
    consumed: Decimal,
) -> None:
    """Move `consumed` into spent and release the reservation. Runs in the caller's transaction."""
    consumed = consumed.quantize(_PLACES)
    for item in reservation:
        held = Decimal(item["amount"])
        await session.execute(
            update(TenantBudgetPeriod)
            .where(
                TenantBudgetPeriod.tenant_id == tenant_id,
                TenantBudgetPeriod.period == item["period"],
                TenantBudgetPeriod.period_start == date.fromisoformat(item["period_start"]),
            )
            .values(
                spent_usd=TenantBudgetPeriod.spent_usd + consumed,
                reserved_usd=case(
                    (TenantBudgetPeriod.reserved_usd - held < 0, Decimal(0)),
                    else_=TenantBudgetPeriod.reserved_usd - held,
                ),
                updated_at=utcnow(),
            )
            .execution_options(synchronize_session=False)
        )


async def release_stale(session: AsyncSession, *, older_than_s: int) -> int:
    """Settle reservations held by pending requests that can no longer be running.

    What such a request consumed is unknown (it may have called a provider before the process
    died), so the whole hold is charged as spent rather than released as free. The executor
    never lets a request draw more than its reservation, so this is an upper bound.
    """
    cutoff = utcnow() - timedelta(seconds=older_than_s)
    stale = (
        await session.scalars(
            select(RequestLog).where(
                and_(
                    RequestLog.status == "pending",
                    RequestLog.created_at < cutoff,
                    RequestLog.budget_reservation.is_not(None),
                )
            )
        )
    ).all()
    for log in stale:
        reservation = list(log.budget_reservation or [])
        held = max((Decimal(item["amount"]) for item in reservation), default=Decimal(0))
        await settle(session, log.tenant_id, reservation, held)
        log.budget_reservation = None
        log.status = "failed"
        log.error_code = "ABANDONED_RESERVATION_CHARGED"
        log.cost_status = "unavailable"
        log.list_cost_status = "unavailable"
        log.completed_at = utcnow()
    await session.commit()
    return len(stale)
