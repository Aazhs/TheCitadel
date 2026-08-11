"""Guild settings CRUD service layer.

All functions acquire their own AsyncSession, commit, and close — keeping the
service stateless and safe for concurrent Discord events.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from src.db.engine import get_session_factory
from src.db.models import GuildSettings

logger = logging.getLogger("arena.services.guild_settings")


async def get_or_create(guild_id: str) -> GuildSettings:
    """Return the guild settings row, creating one with defaults if missing."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == guild_id)
        result = await session.execute(stmt)
        settings = result.scalar_one_or_none()

        if settings is None:
            settings = GuildSettings(discord_guild_id=guild_id)
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
            logger.info("Created guild_settings for guild %s", guild_id)

        return settings


async def get_settings(guild_id: str) -> GuildSettings | None:
    """Return the guild settings row or None."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == guild_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def update_timezone(guild_id: str, timezone: str) -> GuildSettings:
    """Set the timezone for the guild."""
    factory = get_session_factory()
    async with factory() as session:
        settings = await _ensure_row(session, guild_id)
        settings.timezone = timezone
        await session.commit()
        await session.refresh(settings)
        return settings


async def update_channel(guild_id: str, field: str, channel_id: str) -> GuildSettings:
    """Set one of the channel columns and return the updated row.

    Args:
        guild_id: Discord guild snowflake.
        field: One of ``onboarding_channel_id``, ``announcement_channel_id``,
               ``contest_alert_channel_id``.
        channel_id: Discord channel snowflake.

    Returns:
        The updated GuildSettings row.

    Raises:
        ValueError: If *field* is not a valid channel column.
    """
    valid_fields = {
        "onboarding_channel_id",
        "announcement_channel_id",
        "contest_alert_channel_id",
    }
    if field not in valid_fields:
        raise ValueError(f"Invalid channel field: {field!r}")

    factory = get_session_factory()
    async with factory() as session:
        settings = await _ensure_row(session, guild_id)
        setattr(settings, field, channel_id)
        await session.commit()
        await session.refresh(settings)
        logger.info("Updated %s=%s for guild %s", field, channel_id, guild_id)
        return settings


async def update_alert_role(guild_id: str, role_id: str) -> GuildSettings:
    """Set the alert_role_id and return the updated row."""
    factory = get_session_factory()
    async with factory() as session:
        settings = await _ensure_row(session, guild_id)
        settings.alert_role_id = role_id
        await session.commit()
        await session.refresh(settings)
        logger.info("Updated alert_role_id=%s for guild %s", role_id, guild_id)
        return settings


async def reset_settings(guild_id: str) -> GuildSettings | None:
    """Null all channel/role columns but keep the row and timezone.

    Returns the updated row, or None if the guild has no settings row.
    """
    factory = get_session_factory()
    async with factory() as session:
        settings = await _get_row(session, guild_id)
        if settings is None:
            return None

        settings.onboarding_channel_id = None
        settings.announcement_channel_id = None
        settings.contest_alert_channel_id = None
        settings.alert_role_id = None
        settings.auto_create_events = False
        settings.last_auto_event_run = None
        settings.reminders_enabled = True
        await session.commit()
        await session.refresh(settings)
        logger.info("Reset guild_settings for guild %s", guild_id)
        return settings


# ── internal helpers ─────────────────────────────────────────────────


async def _get_row(session, guild_id: str) -> GuildSettings | None:  # type: ignore[type-arg]
    """Fetch the row inside an existing session."""
    stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == guild_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _ensure_row(session, guild_id: str) -> GuildSettings:  # type: ignore[type-arg]
    """Fetch or create inside an existing session (does NOT commit)."""
    settings = await _get_row(session, guild_id)
    if settings is None:
        settings = GuildSettings(discord_guild_id=guild_id)
        session.add(settings)
        await session.flush()
    return settings


async def update_auto_events(guild_id: str, enabled: bool) -> GuildSettings:
    factory = get_session_factory()
    async with factory() as session:
        settings = await _ensure_row(session, guild_id)
        settings.auto_create_events = enabled
        await session.commit()
        await session.refresh(settings)
        return settings

async def update_last_auto_event_run(guild_id: str, timestamp) -> GuildSettings:
    factory = get_session_factory()
    async with factory() as session:
        settings = await _ensure_row(session, guild_id)
        settings.last_auto_event_run = timestamp
        await session.commit()
        await session.refresh(settings)
        return settings

async def update_reminders(guild_id: str, enabled: bool) -> GuildSettings:
    factory = get_session_factory()
    async with factory() as session:
        settings = await _ensure_row(session, guild_id)
        settings.reminders_enabled = enabled
        await session.commit()
        await session.refresh(settings)
        return settings
