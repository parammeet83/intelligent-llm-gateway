from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Tenant
from app.db.session import create_engine
from app.tenancy import rate_limit

T0 = datetime(2026, 11, 4, 12, 0, 15, tzinfo=UTC)


async def _tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(slug=f"rl-{uuid.uuid4().hex[:8]}", name="RL")
    session.add(tenant)
    await session.commit()
    return tenant


async def test_fixed_window_counts_and_resets(session: AsyncSession) -> None:
    tenant = await _tenant(session)
    results = [await rate_limit.hit(session, tenant.id, 2, now=T0) for _ in range(3)]
    assert [r.allowed for r in results] == [True, True, False]
    assert results[2].count == 3 and results[2].retry_after_s == 45
    next_minute = await rate_limit.hit(session, tenant.id, 2, now=T0 + timedelta(minutes=1))
    assert next_minute.allowed and next_minute.count == 1


async def test_tenants_have_independent_windows(session: AsyncSession) -> None:
    a, b = await _tenant(session), await _tenant(session)
    await rate_limit.hit(session, a.id, 1, now=T0)
    assert not (await rate_limit.hit(session, a.id, 1, now=T0)).allowed
    assert (await rate_limit.hit(session, b.id, 1, now=T0)).allowed


async def test_concurrent_hits_are_counted_exactly(database_url: str) -> None:
    engine = create_engine(database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as setup:
            tenant = await _tenant(setup)

        async def one() -> rate_limit.RateLimitResult:
            async with maker() as s:
                return await rate_limit.hit(s, tenant.id, 5, now=T0)

        results = await asyncio.gather(*(one() for _ in range(12)))
        assert sorted(r.count for r in results) == list(range(1, 13))
        assert sum(r.allowed for r in results) == 5
    finally:
        await engine.dispose()


async def test_prune_removes_old_windows(session: AsyncSession) -> None:
    tenant = await _tenant(session)
    await rate_limit.hit(session, tenant.id, 5, now=datetime.now(UTC) - timedelta(days=3))
    await rate_limit.hit(session, tenant.id, 5)
    assert await rate_limit.prune(session) == 1
