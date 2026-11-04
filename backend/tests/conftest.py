"""Shared fixtures.

Every DB test runs against SQLite. When TEST_DATABASE_URL is set (CI's Postgres service, or a
dedicated Neon branch), DB tests also run against PostgreSQL.

TEST_DATABASE_URL must point at a disposable database: the fixtures drop and recreate the schema.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.migrations import alembic_config
from app.db.session import create_engine

TEST_PEPPER = "test-pepper"


def _postgres_url() -> str | None:
    url = os.environ.get("TEST_DATABASE_URL")
    if url and url == os.environ.get("DATABASE_URL"):
        raise RuntimeError("TEST_DATABASE_URL must not equal DATABASE_URL (tests drop the schema)")
    return url


def migrate(url: str, revision: str = "head") -> None:
    cfg = alembic_config()
    cfg.attributes["database_url"] = url
    cfg.attributes["skip_logging_config"] = True
    command.upgrade(cfg, revision)


def downgrade_all(url: str) -> None:
    cfg = alembic_config()
    cfg.attributes["database_url"] = url
    cfg.attributes["skip_logging_config"] = True
    command.downgrade(cfg, "base")


async def _truncate_all(url: str) -> None:
    engine = create_engine(url)
    try:
        async with engine.begin() as conn:
            names = ", ".join(t.name for t in Base.metadata.sorted_tables)
            await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def _postgres_migrated() -> str | None:
    url = _postgres_url()
    if url:
        downgrade_all(url)
        migrate(url)
    return url


@pytest.fixture(params=["sqlite", "postgres"])
def database_url(
    request: pytest.FixtureRequest, tmp_path: Path, _postgres_migrated: str | None
) -> Iterator[str]:
    """A freshly migrated, empty database URL."""
    if request.param == "sqlite":
        url = f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"
        migrate(url)
        yield url
        return
    if not _postgres_migrated:
        pytest.skip("TEST_DATABASE_URL not set")
    asyncio.run(_truncate_all(_postgres_migrated))
    yield _postgres_migrated


@pytest.fixture
async def session(database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_engine(database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as s:
            yield s
    finally:
        await engine.dispose()


def make_settings(database_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "database_url": database_url,
        "api_key_pepper": TEST_PEPPER,
        "admin_token": "test-admin-token",
    }
    values.update(overrides)
    # _env_file=None: tests must never pick up the developer's real .env.
    settings_cls: Any = Settings
    return cast(Settings, settings_cls(_env_file=None, **values))
