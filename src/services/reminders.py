"""Service for managing automated contest reminders."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import joinedload

from src.db.engine import get_session_factory
from src.db.models import Contest, GuildSettings, NotificationDelivery

logger = logging.getLogger("arena.services.reminders")


async def schedule_missing_deliveries() -> int:
    """Scan all upcoming contests and guilds to schedule missing reminders.

    Returns:
        Number of new notification deliveries scheduled.
    """
    now = datetime.now(UTC)
    scheduled_count = 0

    async with get_session_factory()() as session:
        # Find all upcoming contests that haven't started yet
        stmt_contests = select(Contest).where(Contest.start_time_utc > now)
        upcoming_contests = (await session.scalars(stmt_contests)).all()

        if not upcoming_contests:
            return 0

        # Find all guilds that have reminders enabled
        stmt_guilds = select(GuildSettings).where(GuildSettings.reminders_enabled.is_(True))
        guilds = (await session.scalars(stmt_guilds)).all()

        if not guilds:
            return 0

        # For each contest + guild combination, insert the 3 reminder types if they don't exist
        # We use an UPSERT (ON CONFLICT DO NOTHING) because we have a unique constraint.
        reminder_types = [
            ("24h", timedelta(hours=24)),
            ("1h", timedelta(hours=1)),
            ("10m", timedelta(minutes=10)),
        ]

        # Batch insert using PostgreSQL's ON CONFLICT DO NOTHING
        deliveries = []
        for contest in upcoming_contests:
            for n_type, offset in reminder_types:
                scheduled_for = contest.start_time_utc - offset

                # If it's already past due for scheduling (e.g. contest starts in 5 mins and this is the 1h reminder),
                # we do NOT schedule it if it's already past by a large margin.
                # Actually, the background worker handles sending due reminders,
                # but we shouldn't schedule a 24h reminder if the contest is in 5 mins.
                if scheduled_for < now - timedelta(hours=1):
                    # If we missed the window by more than 1 hour, don't schedule it retroactively
                    # to prevent a flood of stale reminders.
                    continue

                for guild in guilds:
                    deliveries.append(
                        {
                            "guild_settings_id": guild.id,
                            "contest_id": contest.id,
                            "notification_type": n_type,
                            "scheduled_for_utc": scheduled_for,
                            "status": "PENDING",
                        }
                    )

        if not deliveries:
            return 0

        # PostgreSQL upsert (ignore conflict on unique constraint)
        stmt = insert(NotificationDelivery).values(deliveries)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["guild_settings_id", "contest_id", "notification_type"]
        )

        result = await session.execute(stmt)
        await session.commit()

        scheduled_count = result.rowcount

    if scheduled_count > 0:
        logger.info(f"Scheduled {scheduled_count} new contest reminders")

    return scheduled_count


async def get_due_deliveries() -> list[NotificationDelivery]:
    """Get all pending notification deliveries that are due to be sent."""
    now = datetime.now(UTC)

    async with get_session_factory()() as session:
        stmt = (
            select(NotificationDelivery)
            .options(
                joinedload(NotificationDelivery.guild_settings),
                joinedload(NotificationDelivery.contest),
            )
            .where(NotificationDelivery.status == "PENDING")
            .where(NotificationDelivery.scheduled_for_utc <= now)
        )
        return list((await session.scalars(stmt)).all())


async def get_pending_deliveries_for_guild(guild_id: str) -> list[NotificationDelivery]:
    """Get all pending notification deliveries for a specific guild, ordered by schedule time."""
    async with get_session_factory()() as session:
        stmt = (
            select(NotificationDelivery)
            .join(GuildSettings)
            .options(joinedload(NotificationDelivery.contest))
            .where(GuildSettings.discord_guild_id == guild_id)
            .where(NotificationDelivery.status == "PENDING")
            .order_by(NotificationDelivery.scheduled_for_utc.asc())
        )
        return list((await session.scalars(stmt)).all())


async def mark_delivery_status(
    delivery_id: int,
    status: str,
    sent_at: datetime | None = None,
    message_id: str | None = None,
    error: str | None = None,
) -> None:
    """Update the status of a notification delivery."""
    async with get_session_factory()() as session:
        stmt = select(NotificationDelivery).where(NotificationDelivery.id == delivery_id)
        delivery = await session.scalar(stmt)
        if delivery:
            delivery.status = status
            if sent_at:
                delivery.sent_at = sent_at
            if message_id:
                delivery.discord_message_id = message_id
            if error:
                delivery.error_message = error
            await session.commit()


async def set_reminders_enabled(guild_id: str, enabled: bool) -> bool:
    """Set whether contest reminders are enabled for a guild.

    Returns:
        True if the guild settings were found and updated, False otherwise.
    """
    async with get_session_factory()() as session:
        stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == guild_id)
        settings = await session.scalar(stmt)
        if not settings:
            return False

        settings.reminders_enabled = enabled
        await session.commit()
        return True
