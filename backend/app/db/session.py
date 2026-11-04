"""Async engine/session factory.

Neon hands out libpq-style URLs (`postgresql://...?sslmode=require&channel_binding=require`).
asyncpg doesn't accept those query parameters, so `normalize_database_url` rewrites the driver
and turns `sslmode` into an `ssl` connect argument.
"""

from __future__ import annotations

import ssl
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding", "sslrootcert", "options"}
_SSL_MODES_REQUIRING_TLS = {"require", "verify-ca", "verify-full"}


@dataclass(frozen=True)
class NormalizedUrl:
    url: str
    connect_args: dict[str, Any] = field(default_factory=dict)

    @property
    def dialect(self) -> str:
        return self.url.split(":", 1)[0].split("+", 1)[0]


def normalize_database_url(raw: str) -> NormalizedUrl:
    parts = urlsplit(raw)
    scheme = parts.scheme
    if scheme in {"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        scheme = "postgresql+asyncpg"
    elif scheme == "sqlite":
        scheme = "sqlite+aiosqlite"

    if not scheme.startswith("postgresql+asyncpg"):
        # urlunsplit would drop the "//" of host-less URLs like sqlite:///path, so swap the
        # scheme textually instead of rebuilding the URL.
        return NormalizedUrl(scheme + raw[len(parts.scheme) :])

    query = dict(parse_qsl(parts.query))
    sslmode = query.get("sslmode", "")
    kept = {k: v for k, v in query.items() if k not in _LIBPQ_ONLY_PARAMS}
    connect_args: dict[str, Any] = {}

    if sslmode in _SSL_MODES_REQUIRING_TLS:
        # Certificate verification is on; Neon presents publicly trusted certificates.
        connect_args["ssl"] = ssl.create_default_context()
    elif sslmode == "disable":
        connect_args["ssl"] = False

    if parts.hostname and "-pooler" in parts.hostname:
        # Neon's pooled endpoint is PgBouncer in transaction mode. Unique statement names
        # avoid prepared-statement collisions between pooled server connections.
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = lambda: f"__rw_{uuid.uuid4().hex}__"
        kept["prepared_statement_cache_size"] = "0"

    url = urlunsplit(parts._replace(scheme=scheme, query=urlencode(kept)))
    return NormalizedUrl(url, connect_args)


def create_engine(raw_url: str, *, echo: bool = False) -> AsyncEngine:
    normalized = normalize_database_url(raw_url)
    kwargs: dict[str, Any] = {"echo": echo, "connect_args": normalized.connect_args}
    if normalized.dialect == "postgresql":
        # Neon suspends idle computes and drops their connections; detect and recycle stale ones.
        kwargs.update(pool_pre_ping=True, pool_recycle=300, pool_size=5, max_overflow=5)
    engine = create_async_engine(normalized.url, **kwargs)
    if normalized.dialect == "sqlite":
        # SQLite ignores foreign keys unless asked, which would hide CASCADE/RESTRICT bugs in tests.
        event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Database:
    """Owns the engine and session factory for the lifetime of the app."""

    def __init__(self, raw_url: str, *, echo: bool = False) -> None:
        self.engine = create_engine(raw_url, echo=echo)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
