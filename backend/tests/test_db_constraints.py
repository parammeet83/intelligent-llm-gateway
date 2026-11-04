"""The schema itself enforces the invariants the accounting code relies on."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RequestLog, Tenant


async def _tenant(session: AsyncSession) -> Tenant:
    tenant = Tenant(slug=f"t-{uuid.uuid4().hex[:8]}", name="Test")
    session.add(tenant)
    await session.flush()
    return tenant


async def test_duplicate_client_request_id_rejected_within_tenant(session: AsyncSession) -> None:
    tenant = await _tenant(session)
    session.add(RequestLog(tenant_id=tenant.id, client_request_id="req-1"))
    await session.flush()
    session.add(RequestLog(tenant_id=tenant.id, client_request_id="req-1"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_same_client_request_id_allowed_across_tenants(session: AsyncSession) -> None:
    a, b = await _tenant(session), await _tenant(session)
    session.add_all(
        [
            RequestLog(tenant_id=a.id, client_request_id="req-1"),
            RequestLog(tenant_id=b.id, client_request_id="req-1"),
        ]
    )
    await session.flush()


@pytest.mark.parametrize("field", ["cost_status", "list_cost_status", "status"])
async def test_unknown_status_values_rejected(session: AsyncSession, field: str) -> None:
    tenant = await _tenant(session)
    log = RequestLog(tenant_id=tenant.id)
    setattr(log, field, "made_up")
    session.add(log)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_defaults_do_not_claim_a_cost(session: AsyncSession) -> None:
    tenant = await _tenant(session)
    log = RequestLog(tenant_id=tenant.id)
    session.add(log)
    await session.flush()
    assert log.actual_charge_usd is None
    assert log.cost_status == "unavailable"
    assert log.list_cost_status == "unavailable"
