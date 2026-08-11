"""Audit logging service layer.

All functions acquire their own AsyncSession, commit, and close — keeping the
service stateless and safe for concurrent Discord events.
"""

from __future__ import annotations

import logging

from src.db.engine import get_session_factory
from src.db.models import AuditLog

logger = logging.getLogger("arena.services.audit")


async def log_action(
    guild_settings_id: int,
    action: str,
    performed_by: str,
    *,
    target_type: str | None = None,
    target_id: int | None = None,
    details: str | None = None,
) -> AuditLog:
    logger.info("Logging audit action: %s for guild_settings_id=%s", action, guild_settings_id)
    factory = get_session_factory()
    async with factory() as session:
        log_entry = AuditLog(
            guild_settings_id=guild_settings_id,
            action=action,
            performed_by_discord_user_id=performed_by,
            target_type=target_type,
            target_id=target_id,
            details=details,
        )
        session.add(log_entry)
        await session.commit()
        await session.refresh(log_entry)
        return log_entry
