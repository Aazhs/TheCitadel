"""Async SQLAlchemy engine and session management for the local SQLite database.

Mirrors the pattern in engine.py but targets a local SQLite file via aiosqlite.
Completely independent of the Postgres engine — separate Base, separate tables.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("arena.db.local_engine")

# Module-level references, initialised by init_local_db() and torn down by close_local_db().
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_local_db(db_path: str) -> None:
    """Create the async SQLite engine, session factory, and run create_all().

    Args:
        db_path: Path to the local SQLite file (e.g. './accountability.db').
    """
    global _engine, _session_factory

    url = f"sqlite+aiosqlite:///{db_path}"

    _engine = create_async_engine(url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    # Idempotent schema creation — no Alembic needed for a solo local DB.
    # Ensure all models are imported so LocalBase.metadata knows about them.
    import src.db.local_models  # noqa: F401
    from src.db.local_base import LocalBase

    async with _engine.begin() as conn:
        await conn.run_sync(LocalBase.metadata.create_all)

    logger.info("Local SQLite database initialised at %s", db_path)


async def close_local_db() -> None:
    """Dispose of the async SQLite engine and release connections."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("Local SQLite database engine closed")
    _engine = None
    _session_factory = None


def get_local_engine() -> AsyncEngine:
    """Return the current local async engine, raising if uninitialised."""
    if _engine is None:
        raise RuntimeError("Local database engine not initialised. Call init_local_db() first.")
    return _engine


def get_local_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the current local session factory, raising if uninitialised."""
    if _session_factory is None:
        raise RuntimeError(
            "Local database session factory not initialised. Call init_local_db() first."
        )
    return _session_factory


async def get_local_session() -> AsyncSession:
    """Convenience: create and return a new local AsyncSession."""
    return get_local_session_factory()()
