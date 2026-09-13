"""Events CRUD service layer.

All functions acquire their own AsyncSession, commit, and close — keeping the
service stateless and safe for concurrent Discord events.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.db.engine import get_session_factory
from src.db.models import Event, EventRegistration, GuildMember, GuildSettings, User

logger = logging.getLogger("arena.services.events")

# Toggle this to require a linked Codeforces account for Codeforces events.
REQUIRE_CF_LINK_FOR_CF_EVENTS: bool = True

# Valid event types
VALID_EVENT_TYPES = frozenset(
    {
        "codeforces_contest",
        "codechef_contest",
        "leetcode_contest",
        "custom_practice",
        "daily_leetcode",
    }
)

# Valid status values
VALID_STATUSES = frozenset(
    {
        "draft",
        "published",
        "registration_open",
        "active",
        "ended",
        "submission_open",
        "finalized",
        "cancelled",
    }
)

# Statuses that allow registration
REGISTRABLE_STATUSES = frozenset({"published", "registration_open"})


async def create_event(
    guild_id: str,
    title: str,
    event_type: str,
    description: str,
    start_time_utc: datetime,
    end_time_utc: datetime,
    created_by_discord_user_id: str,
    *,
    platform: str | None = None,
    official_url: str | None = None,
    registration_deadline_utc: datetime | None = None,
    announcement_channel_id: str | None = None,
    discussion_channel_id: str | None = None,
    results_channel_id: str | None = None,
) -> Event:
    """Create a new event in draft status.

    Raises:
        ValueError: If event_type is invalid or end_time <= start_time.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event type: {event_type!r}")
    if end_time_utc <= start_time_utc:
        raise ValueError("end_time must be after start_time")

    factory = get_session_factory()
    async with factory() as session:
        # Ensure guild settings exist
        stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == guild_id)
        result = await session.execute(stmt)
        gs = result.scalar_one_or_none()
        if gs is None:
            gs = GuildSettings(discord_guild_id=guild_id)
            session.add(gs)
            await session.flush()

        event = Event(
            guild_settings_id=gs.id,
            title=title,
            event_type=event_type,
            platform=platform,
            status="draft",
            description=description,
            official_url=official_url,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
            registration_deadline_utc=registration_deadline_utc,
            announcement_channel_id=announcement_channel_id,
            discussion_channel_id=discussion_channel_id,
            results_channel_id=results_channel_id,
            created_by_discord_user_id=created_by_discord_user_id,
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        logger.info("Created event %s (%r) for guild %s", event.id, title, guild_id)
        return event


async def update_event(
    event_id: int,
    guild_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    official_url: str | None = None,
    start_time_utc: datetime | None = None,
    end_time_utc: datetime | None = None,
) -> Event:
    """Update editable fields of an event.

    Raises:
        ValueError: If event doesn't exist, or end_time <= start_time.
    """
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(Event)
            .join(GuildSettings)
            .where(Event.id == event_id, GuildSettings.discord_guild_id == guild_id)
        )
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if event is None:
            raise ValueError(f"Event {event_id} not found")

        if title is not None:
            event.title = title
        if description is not None:
            event.description = description
        if official_url is not None:
            event.official_url = official_url

        new_start = start_time_utc or event.start_time_utc
        new_end = end_time_utc or event.end_time_utc
        if new_end <= new_start:
            raise ValueError("end_time must be after start_time")

        if start_time_utc is not None:
            event.start_time_utc = start_time_utc
        if end_time_utc is not None:
            event.end_time_utc = end_time_utc

        await session.commit()
        await session.refresh(event)
        logger.info("Updated event %s", event_id)
        return event


async def get_event(event_id: int, guild_id: str) -> Event | None:
    """Fetch an event by PK, scoped to the given guild."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(Event)
            .join(GuildSettings)
            .where(Event.id == event_id, GuildSettings.discord_guild_id == guild_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def list_events(guild_id: str, *, include_ended: bool = False) -> list[Event]:
    """List events for a guild, optionally excluding ended/cancelled ones."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Event).join(GuildSettings).where(GuildSettings.discord_guild_id == guild_id)
        if not include_ended:
            stmt = stmt.where(
                Event.status.notin_(["ended", "cancelled"]),
                Event.end_time_utc > func.now(),
            )
        stmt = stmt.order_by(Event.start_time_utc.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def publish_event(event_id: int, guild_id: str) -> Event:
    """Transition an event from draft → published.

    Raises:
        ValueError: If the event doesn't exist or is not in draft status.
    """
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(Event)
            .join(GuildSettings)
            .where(Event.id == event_id, GuildSettings.discord_guild_id == guild_id)
        )
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if event is None:
            raise ValueError(f"Event {event_id} not found")
        if event.status != "draft":
            raise ValueError(f"Cannot publish event in '{event.status}' status (must be 'draft')")

        event.status = "published"
        await session.commit()
        await session.refresh(event)
        logger.info("Published event %s", event_id)
        return event


async def cancel_event(event_id: int, guild_id: str) -> Event:
    """Cancel an event.

    Raises:
        ValueError: If the event doesn't exist or is already cancelled/ended.
    """
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(Event)
            .join(GuildSettings)
            .where(Event.id == event_id, GuildSettings.discord_guild_id == guild_id)
        )
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if event is None:
            raise ValueError(f"Event {event_id} not found")
        if event.status in ("cancelled", "ended"):
            raise ValueError(f"Cannot cancel event in '{event.status}' status")

        event.status = "cancelled"
        await session.commit()
        await session.refresh(event)
        logger.info("Cancelled event %s", event_id)
        return event


async def update_announcement_message_id(event_id: int, message_id: str) -> None:
    """Store the Discord announcement message ID on an event."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Event).where(Event.id == event_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()
        if event:
            event.announcement_message_id = message_id
            await session.commit()


async def register_for_event(
    event_id: int,
    guild_id: str,
    user_id: str,
) -> EventRegistration:
    """Register a member for an event.

    Validates event state, deadlines, and duplicate registrations.

    Raises:
        ValueError: If event doesn't exist, isn't registrable, deadline passed,
                    or user is already registered.
    """
    factory = get_session_factory()
    async with factory() as session:
        # Fetch event scoped to guild
        stmt = (
            select(Event)
            .join(GuildSettings)
            .where(Event.id == event_id, GuildSettings.discord_guild_id == guild_id)
        )
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if event is None:
            raise ValueError(f"Event {event_id} not found")
        if event.status not in REGISTRABLE_STATUSES:
            raise ValueError(f"Registration is not open for this event (status: {event.status})")
        if event.registration_deadline_utc and datetime.now(UTC) > event.registration_deadline_utc:
            raise ValueError("Registration deadline has passed")

        # Ensure User row
        stmt_u = select(User).where(User.discord_user_id == user_id)
        result_u = await session.execute(stmt_u)
        user = result_u.scalar_one_or_none()
        if user is None:
            user = User(discord_user_id=user_id)
            session.add(user)
            await session.flush()

        # Ensure GuildMember row
        stmt_gm = select(GuildMember).where(
            GuildMember.guild_settings_id == event.guild_settings_id,
            GuildMember.user_id == user.id,
        )
        result_gm = await session.execute(stmt_gm)
        member = result_gm.scalar_one_or_none()
        if member is None:
            member = GuildMember(guild_settings_id=event.guild_settings_id, user_id=user.id)
            session.add(member)
            await session.flush()

        # Check for duplicate registration
        stmt_reg = select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.guild_member_id == member.id,
        )
        result_reg = await session.execute(stmt_reg)
        existing = result_reg.scalar_one_or_none()
        if existing is not None:
            raise ValueError("You are already registered for this event")

        registration = EventRegistration(
            event_id=event_id,
            guild_member_id=member.id,
            status="registered",
        )
        session.add(registration)

        try:
            await session.commit()
            await session.refresh(registration)
            logger.info(
                "User %s registered for event %s in guild %s",
                user_id,
                event_id,
                guild_id,
            )
            return registration
        except IntegrityError as e:
            await session.rollback()
            raise ValueError("You are already registered for this event") from e


async def get_user_events(guild_id: str, user_id: str) -> list[Event]:
    """Get all events the user is registered for in a guild."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(Event)
            .join(EventRegistration)
            .join(GuildMember)
            .join(GuildSettings)
            .join(User, GuildMember.user_id == User.id)
            .where(
                GuildSettings.discord_guild_id == guild_id,
                User.discord_user_id == user_id,
            )
            .order_by(Event.start_time_utc.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def is_registered(event_id: int, guild_member_id: int) -> bool:
    """Check whether a guild member is registered for an event."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.guild_member_id == guild_member_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None


async def get_registration_count(event_id: int) -> int:
    """Return the number of registrations for an event."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(func.count())
            .select_from(EventRegistration)
            .where(EventRegistration.event_id == event_id)
        )
        result = await session.execute(stmt)
        return result.scalar_one()
