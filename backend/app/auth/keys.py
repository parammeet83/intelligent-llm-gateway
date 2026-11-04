"""Tenant API-key lifecycle: create, list, revoke, rotate, authenticate.

Plaintext keys exist only in the return value of create/rotate and are never stored or logged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_keys import generate_api_key, parse_prefix, verify_api_key
from app.db.base import utcnow
from app.db.models import ApiKey, Tenant


@dataclass(frozen=True)
class IssuedKey:
    key: ApiKey
    plaintext: str  # show once


@dataclass(frozen=True)
class AuthenticatedTenant:
    tenant: Tenant
    api_key_id: uuid.UUID | None  # None for internal callers (benchmark runner)
    key_prefix: str


def _aware(value: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes; everything is stored in UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=utcnow().tzinfo)
    return value


def key_is_active(key: ApiKey, now: datetime) -> bool:
    if key.revoked_at is not None:
        return False
    expires = _aware(key.expires_at)
    return expires is None or expires > now


async def issue_key(session: AsyncSession, tenant: Tenant, name: str, pepper: str) -> IssuedKey:
    generated = generate_api_key(pepper)
    key = ApiKey(
        tenant_id=tenant.id, name=name, key_prefix=generated.prefix, key_hash=generated.key_hash
    )
    session.add(key)
    await session.flush()
    return IssuedKey(key=key, plaintext=generated.plaintext)


async def revoke_key(session: AsyncSession, key: ApiKey) -> None:
    if key.revoked_at is None:
        key.revoked_at = utcnow()


async def rotate_key(
    session: AsyncSession, key: ApiKey, tenant: Tenant, pepper: str, *, grace_s: int = 0
) -> IssuedKey:
    """Issue a replacement. The old key stops working now, or after `grace_s` seconds."""
    issued = await issue_key(session, tenant, key.name, pepper)
    if grace_s > 0:
        key.expires_at = utcnow() + timedelta(seconds=grace_s)
    else:
        key.revoked_at = utcnow()
    return issued


async def authenticate(
    session: AsyncSession, presented: str, pepper: str, *, touch_interval_s: int
) -> AuthenticatedTenant | None:
    """Return the tenant for a valid, active key; None for anything else (no detail leaked)."""
    prefix = parse_prefix(presented)
    if prefix is None:
        return None
    row = (
        await session.execute(
            select(ApiKey, Tenant)
            .join(Tenant, Tenant.id == ApiKey.tenant_id)
            .where(ApiKey.key_prefix == prefix)
        )
    ).first()
    if row is None:
        return None
    key, tenant = row
    now = utcnow()
    if not verify_api_key(presented, key.key_hash, pepper):
        return None
    if not key_is_active(key, now) or tenant.status != "active":
        return None
    last = _aware(key.last_used_at)
    if last is None or (now - last).total_seconds() >= touch_interval_s:
        key.last_used_at = now
        await session.commit()
    return AuthenticatedTenant(tenant=tenant, api_key_id=key.id, key_prefix=key.key_prefix)
