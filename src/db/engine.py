"""Async SQLAlchemy engine and session management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("arena.db.engine")

# Module-level references, initialised by init_db() and torn down by close_db().
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str) -> None:
    """Create the async engine and session factory.

    Args:
        database_url: A PostgreSQL connection string.
            Accepts ``postgresql://`` or ``postgresql+asyncpg://`` schemes.
    """
    global _engine, _session_factory

    # Normalise scheme for asyncpg driver
    url = database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    _engine = create_async_engine(
        url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        connect_args={
            "prepared_statement_cache_size": 0,
            "statement_cache_size": 0,
        }
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    logger.info("Database engine initialised")


async def close_db() -> None:
    """Dispose of the async engine and release connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("Database engine closed")
    _engine = None
    _session_factory = None


def get_engine() -> AsyncEngine:
    """Return the current async engine, raising if uninitialised."""
    if _engine is None:
        raise RuntimeError("Database engine not initialised. Call init_db() first.")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the current session factory, raising if uninitialised."""
    if _session_factory is None:
        raise RuntimeError("Database session factory not initialised. Call init_db() first.")
    return _session_factory


async def get_session() -> AsyncSession:
    """Convenience: create and return a new AsyncSession."""
    return get_session_factory()()
