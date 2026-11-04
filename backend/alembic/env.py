"""Alembic environment. Uses the app's settings and URL normalisation so migrations connect
exactly the way the app does (including Neon's TLS requirements).

URL precedence: `-x db_url=...` > an engine/URL passed by tests via `config.attributes` > settings.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.db import models  # noqa: F401 - registers tables on Base.metadata
from app.db.base import Base
from app.db.session import create_engine, normalize_database_url

config = context.config
if config.config_file_name and not config.attributes.get("skip_logging_config"):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    cli_url = context.get_x_argument(as_dictionary=True).get("db_url")
    if cli_url:
        return cli_url
    attr_url = config.attributes.get("database_url")
    if attr_url:
        return str(attr_url)
    return get_settings().database_url.get_secret_value()


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        literal_binds=connection is None,
        compare_type=True,
        # SQLite can't ALTER most constraints in place; batch mode rebuilds the table.
        render_as_batch=True,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout (`alembic upgrade head --sql`) without connecting."""
    _configure(url=normalize_database_url(_database_url()).url)
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(_database_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync)
            await connection.commit()
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
