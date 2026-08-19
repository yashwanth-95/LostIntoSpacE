"""Alembic environment.

SINGLE DRIVER, ON PURPOSE. Both the application and these migrations run on
`asyncpg`. The more commonly documented pattern is asyncpg for the app plus
psycopg2 for Alembic, and KNOWN_ISSUES D-5 originally planned for that split.
Using Alembic's native async support instead removes the split entirely: one
dependency, no URL rewriting between drivers, and no chance of someone later
"fixing" the two URLs into agreement and breaking one of them.

The database URL comes from the environment via the application's Settings, so
alembic.ini holds no credentials.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.core.config import get_settings

# Importing the model registry is what populates Base.metadata. If a model is
# not reachable from src.models, autogenerate will not see it.
from src.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", get_settings().database_url)


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Detect column type changes and server-default changes in autogenerate.
        # Still review every generated revision by hand: autogenerate does not
        # reliably detect CHECK constraints or partial indexes.
        compare_type=True,
        compare_server_default=True,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a database connection (`alembic upgrade --sql`)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
