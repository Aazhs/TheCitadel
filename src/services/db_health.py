"""Database health-check service."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy import text

from src.db.engine import get_engine

logger = logging.getLogger("arena.services.db_health")


@dataclass(frozen=True)
class DbHealthResult:
    """Result of a database connectivity check."""

    healthy: bool
    latency_ms: float
    server_version: str
    error: str | None = None


async def check_db_health() -> DbHealthResult:
    """Test database connectivity and return a health result.

    Does NOT expose connection strings or secrets.
    """
    start = time.monotonic()
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            row = await conn.execute(text("SELECT version()"))
            version = row.scalar_one()
            latency = (time.monotonic() - start) * 1000
            logger.info("Database health check OK — latency=%.1fms", latency)
            return DbHealthResult(
                healthy=True,
                latency_ms=round(latency, 1),
                server_version=str(version),
            )
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        logger.warning("Database health check FAILED: %s", exc)
        return DbHealthResult(
            healthy=False,
            latency_ms=round(latency, 1),
            server_version="unknown",
            error=str(exc),
        )
