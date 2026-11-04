"""Per-tenant fixed-window rate limiting (requests per UTC minute).

One atomic `INSERT ... ON CONFLICT DO UPDATE ... RETURNING request_count` per request. The database
serialises concurrent increments of the same row, so the count is exact across processes and
instances, with no Redis. Trade-off: a fixed window allows up to 2x the limit across a minute
boundary, and every request costs one extra write.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models import RateLimitWindow


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    limit: int
    retry_after_s: int


async def hit(
    session: AsyncSession, tenant_id: uuid.UUID, limit_rpm: int, *, now: datetime | None = None
) -> RateLimitResult:
    current = now or utcnow()
    window = current.replace(second=0, microsecond=0)
    dialect = session.bind.dialect.name if session.bind else "sqlite"
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
    stmt = (
        insert(RateLimitWindow)
        .values(tenant_id=tenant_id, window_start=window, request_count=1)
        .on_conflict_do_update(
            index_elements=[RateLimitWindow.tenant_id, RateLimitWindow.window_start],
            set_={"request_count": RateLimitWindow.request_count + 1},
        )
        .returning(RateLimitWindow.request_count)
    )
    count = int((await session.execute(stmt)).scalar_one())
    await session.commit()
    return RateLimitResult(
        allowed=count <= limit_rpm,
        count=count,
        limit=limit_rpm,
        retry_after_s=max(1, 60 - current.second),
    )


async def prune(session: AsyncSession, *, older_than: timedelta = timedelta(days=1)) -> int:
    result = await session.execute(
        delete(RateLimitWindow).where(RateLimitWindow.window_start < utcnow() - older_than)
    )
    await session.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
