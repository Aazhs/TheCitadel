"""Alembic environment configuration for async migrations."""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Add project root to path so we can import our models
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db.base import Base

# Import all models so they register with Base.metadata
from src.db.models import (  # noqa: F401
    AuditLog,
    Contest,
    Event,
    EventLeaderboardEntry,
    EventRegistration,
    EventSubmission,
    GuildMember,
    GuildSettings,
    LinkedAccount,
    NotificationDelivery,
    
    User,
)

# Load environment variables from .env file for local development
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

config = context.config

# Override sqlalchemy.url with DATABASE_URL from environment
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Alembic requires a database connection string. "
        "Ensure your .env file exists and contains DATABASE_URL."
    )

# Ensure the URL uses the asyncpg driver for async operations
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Alembic uses Python's configparser, which treats '%' as an interpolation character.
# We must escape '%' as '%%' so that URL-encoded passwords (like '%40' for '@') don't crash it.
escaped_url = database_url.replace("%", "%%")
config.set_main_option("sqlalchemy.url", escaped_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL scripts without connecting to the database.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations using the given connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
