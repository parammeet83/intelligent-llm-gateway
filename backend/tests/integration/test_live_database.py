"""Non-destructive checks against the real configured database (DATABASE_URL, e.g. Neon).

Opt-in:  $env:RUN_LIVE_DB_TESTS = "1"; uv run pytest tests/integration -q

Safety:
- Never truncates, drops, or migrates.
- Every test runs inside one outer transaction that is always rolled back, so nothing it writes is
  ever committed. Expected failures happen inside SAVEPOINTs, keeping the outer transaction usable.
- Only reads committed data otherwise.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.config import get_settings
from app.db.base import Base
from app.db.migrations import expected_head
from app.db.models import ApiKey, ProviderModel, RequestAttempt, RequestLog, Tenant
from app.db.session import create_engine
from app.providers.catalog import load_catalog

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_DB_TESTS") != "1",
    reason="live database checks are opt-in (RUN_LIVE_DB_TESTS=1)",
)


@pytest.fixture
async def conn() -> AsyncIterator[AsyncConnection]:
    url = get_settings().database_url.get_secret_value()
    if not url.split(":", 1)[0].startswith("postgres"):
        pytest.skip("DATABASE_URL is not PostgreSQL")
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            try:
                yield connection
            finally:
                await outer.rollback()  # always: nothing from these tests is ever committed
    finally:
        await engine.dispose()


@pytest.fixture
async def session(conn: AsyncConnection) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(
        bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
    ) as s:
        yield s


def _diff(sync_conn: Connection) -> list[Any]:
    ctx = MigrationContext.configure(sync_conn, opts={"compare_type": True})
    diff: list[Any] = compare_metadata(ctx, Base.metadata)
    return diff


async def test_schema_is_at_head_without_drift(conn: AsyncConnection) -> None:
    revision = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
    assert revision == expected_head()
    assert await conn.run_sync(_diff) == []


async def test_timestamps_are_timezone_aware(conn: AsyncConnection) -> None:
    naive = (
        await conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
                "AND data_type = 'timestamp without time zone'"
            )
        )
    ).scalar()
    assert naive == 0


async def test_seeded_registry_is_consistent(session: AsyncSession) -> None:
    rows = {m.key: m for m in (await session.scalars(select(ProviderModel))).all()}
    assert rows, "run `uv run python -m app.cli seed` first"
    catalog = load_catalog(get_settings().model_registry_path)
    for spec in catalog.models:
        row = rows.get(spec.key)
        assert row is not None, f"{spec.key} missing: re-run the seed after registry changes"
        # Priced models link to a snapshot; unpriced ones must not (never a fake $0 price).
        assert (row.pricing_snapshot_id is not None) == (spec.pricing is not None)
        assert row.simulated == (spec.provider == "mock")
        assert row.billing == "free"


async def test_api_keys_are_stored_hashed(session: AsyncSession) -> None:
    for key in (await session.scalars(select(ApiKey))).all():
        assert len(key.key_hash) == 64
        assert key.key_prefix.startswith("rw_")
        assert key.key_prefix not in key.key_hash


async def _scratch_tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(slug=f"live-check-{uuid.uuid4().hex[:10]}", name="Live check (rolled back)")
    session.add(tenant)
    await session.flush()
    return tenant


async def test_duplicate_client_request_id_rejected(session: AsyncSession) -> None:
    tenant = await _scratch_tenant(session)
    session.add(RequestLog(tenant_id=tenant.id, client_request_id="dup"))
    await session.flush()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(RequestLog(tenant_id=tenant.id, client_request_id="dup"))


@pytest.mark.parametrize("field", ["cost_status", "list_cost_status", "status"])
async def test_status_check_constraints_enforced(session: AsyncSession, field: str) -> None:
    tenant = await _scratch_tenant(session)
    log = RequestLog(tenant_id=tenant.id)
    setattr(log, field, "made_up")
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(log)


async def test_tenant_with_request_history_cannot_be_deleted(session: AsyncSession) -> None:
    tenant = await _scratch_tenant(session)
    session.add(RequestLog(tenant_id=tenant.id))
    await session.flush()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.execute(delete(Tenant).where(Tenant.id == tenant.id))


async def test_attempts_cascade_with_their_request(session: AsyncSession) -> None:
    tenant = await _scratch_tenant(session)
    log = RequestLog(tenant_id=tenant.id)
    session.add(log)
    await session.flush()
    session.add(
        RequestAttempt(
            request_id=log.id,
            attempt_number=1,
            provider="mock",
            model_id="mock-small",
            reason_code="PRIMARY",
            status="succeeded",
        )
    )
    await session.flush()
    await session.execute(delete(RequestLog).where(RequestLog.id == log.id))
    remaining = await session.scalar(
        select(func.count()).select_from(RequestAttempt).where(RequestAttempt.request_id == log.id)
    )
    assert remaining == 0
