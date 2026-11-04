import asyncio
from pathlib import Path
from typing import Any

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, inspect

from app.db.base import Base
from app.db.migrations import alembic_config, expected_head
from app.db.session import create_engine
from tests.conftest import downgrade_all, migrate


def _inspect_sync(sync_conn: Connection) -> tuple[list[Any], set[str]]:
    ctx = MigrationContext.configure(sync_conn, opts={"compare_type": True})
    return compare_metadata(ctx, Base.metadata), set(inspect(sync_conn).get_table_names())


async def _diff_and_tables(url: str) -> tuple[list[Any], set[str]]:
    engine = create_engine(url)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(_inspect_sync)
    finally:
        await engine.dispose()


async def test_migrations_match_models(database_url: str) -> None:
    diff, tables = await _diff_and_tables(database_url)
    assert diff == [], f"models and migrations have drifted: {diff}"
    assert {t.name for t in Base.metadata.sorted_tables} <= tables


def test_upgrade_downgrade_roundtrip(tmp_path: Path) -> None:
    # Sync test: Alembic's env.py starts its own event loop.
    url = f"sqlite+aiosqlite:///{(tmp_path / 'rt.db').as_posix()}"
    migrate(url)
    downgrade_all(url)
    _, tables = asyncio.run(_diff_and_tables(url))
    assert tables <= {"alembic_version"}
    migrate(url)
    _, tables = asyncio.run(_diff_and_tables(url))
    assert "request_logs" in tables


def test_single_head() -> None:
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    assert heads == [expected_head()]
    assert command  # imported for parity with CLI usage
