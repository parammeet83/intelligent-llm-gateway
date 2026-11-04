"""Budget reservations at the database level, including concurrency (SQLite + PostgreSQL)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.accounting import budget
from app.db.models import RequestLog, Tenant, TenantBudgetPeriod
from app.db.session import create_engine

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


async def _tenant(session: AsyncSession, daily: str | None, monthly: str | None) -> Tenant:
    tenant = Tenant(
        slug=f"b-{uuid.uuid4().hex[:8]}",
        name="Budget test",
        daily_budget_usd=Decimal(daily) if daily else None,
        monthly_budget_usd=Decimal(monthly) if monthly else None,
    )
    session.add(tenant)
    await session.commit()
    return tenant


async def _periods(session: AsyncSession, tenant: Tenant) -> dict[str, TenantBudgetPeriod]:
    # populate_existing refreshes just these rows (bulk UPDATEs bypass the identity map) without
    # expiring the caller's other objects.
    rows = (
        await session.scalars(
            select(TenantBudgetPeriod)
            .where(TenantBudgetPeriod.tenant_id == tenant.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    return {r.period: r for r in rows}


async def test_no_budget_means_no_enforcement(session: AsyncSession) -> None:
    tenant = await _tenant(session, None, None)
    assert await budget.remaining(session, tenant) is None
    assert await budget.reserve(session, tenant, Decimal("5")) == []


async def test_reserve_settle_moves_reservation_into_spend(session: AsyncSession) -> None:
    tenant = await _tenant(session, "1.00", "10.00")
    reservation = await budget.reserve(session, tenant, Decimal("0.30"), now=NOW)
    assert {r["period"] for r in reservation} == {"daily", "monthly"}
    assert await budget.remaining(session, tenant, now=NOW) == Decimal("0.70")
    await budget.settle(session, tenant.id, reservation, Decimal("0.12"))
    await session.commit()
    periods = await _periods(session, tenant)
    for period in periods.values():
        assert Decimal(period.spent_usd) == Decimal("0.12")
        assert Decimal(period.reserved_usd) == 0
    assert await budget.remaining(session, tenant, now=NOW) == Decimal("0.88")


async def test_exhaustion_is_all_or_nothing_across_periods(session: AsyncSession) -> None:
    tenant = await _tenant(session, "1.00", "0.10")  # monthly is the binding limit
    with pytest.raises(budget.BudgetExhausted) as info:
        await budget.reserve(session, tenant, Decimal("0.50"), now=NOW)
    assert info.value.period == "monthly"
    periods = await _periods(session, tenant)
    assert all(Decimal(p.reserved_usd) == 0 for p in periods.values())  # daily rolled back too


async def test_limit_change_applies_to_current_period(session: AsyncSession) -> None:
    tenant = await _tenant(session, "1.00", None)
    await budget.reserve(session, tenant, Decimal("0.50"), now=NOW)
    tenant.daily_budget_usd = Decimal("0.40")
    await session.commit()
    assert await budget.remaining(session, tenant, now=NOW) == Decimal("-0.10")
    with pytest.raises(budget.BudgetExhausted):
        await budget.reserve(session, tenant, Decimal("0.01"), now=NOW)


async def test_new_day_starts_a_fresh_daily_period(session: AsyncSession) -> None:
    tenant = await _tenant(session, "1.00", None)
    reservation = await budget.reserve(session, tenant, Decimal("1.00"), now=NOW)
    await budget.settle(session, tenant.id, reservation, Decimal("1.00"))
    await session.commit()
    assert await budget.remaining(session, tenant, now=NOW) == 0
    assert await budget.remaining(session, tenant, now=NOW + timedelta(days=1)) == Decimal("1.00")


async def test_concurrent_reservations_never_overspend(database_url: str) -> None:
    engine = create_engine(database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as setup:
            tenant = await _tenant(setup, "1.00", "1.00")

        async def attempt() -> bool:
            async with maker() as s:
                try:
                    await budget.reserve(s, tenant, Decimal("0.10"), now=NOW)
                    return True
                except budget.BudgetExhausted:
                    return False

        outcomes = await asyncio.gather(*(attempt() for _ in range(25)))
        assert sum(outcomes) == 10  # exactly floor(1.00 / 0.10)
        async with maker() as check:
            periods = await _periods(check, tenant)
            for period in periods.values():
                assert Decimal(period.reserved_usd) == Decimal("1.00")
                assert Decimal(period.reserved_usd) <= Decimal(period.limit_usd)
    finally:
        await engine.dispose()


async def test_stale_reservations_are_charged_not_released_as_free(session: AsyncSession) -> None:
    tenant = await _tenant(session, "1.00", None)
    reservation = await budget.reserve(session, tenant, Decimal("0.60"), now=datetime.now(UTC))
    session.add(
        RequestLog(
            tenant_id=tenant.id,
            status="pending",
            budget_reservation=reservation,
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    await session.commit()
    assert await budget.release_stale(session, older_than_s=600) == 1
    # What the abandoned request consumed is unknown, so the hold becomes spend, not free headroom.
    assert await budget.remaining(session, tenant) == Decimal("0.40")
    (period,) = (await _periods(session, tenant)).values()
    assert Decimal(period.spent_usd) == Decimal("0.60")
    assert Decimal(period.reserved_usd) == 0
    log = await session.scalar(select(RequestLog).where(RequestLog.tenant_id == tenant.id))
    assert log is not None and log.status == "failed"
    assert log.error_code == "ABANDONED_RESERVATION_CHARGED"
    assert log.cost_status == "unavailable" and log.list_cost_status == "unavailable"
    assert await budget.release_stale(session, older_than_s=600) == 0  # idempotent
