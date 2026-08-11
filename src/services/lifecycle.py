"""Event lifecycle state-machine service layer.

All functions acquire their own AsyncSession, commit, and close — keeping the
service stateless and safe for concurrent Discord events.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.engine import get_session_factory
from src.db.models import Event

logger = logging.getLogger("arena.services.lifecycle")


async def get_events_to_activate(now: datetime) -> list[Event]:
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(Event)
            .where(Event.status.in_(["published", "registration_open"]))
            .where(Event.start_time_utc <= now)
            .options(selectinload(Event.guild_settings))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_events_to_end(now: datetime) -> list[Event]:
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(Event)
            .where(Event.status == "active")
            .where(Event.end_time_utc <= now)
            .options(selectinload(Event.guild_settings))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_events_to_finalize(now: datetime) -> list[Event]:
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(Event)
            .where(Event.status == "submission_open")
            .where(Event.submission_deadline_utc.is_not(None))
            .where(Event.submission_deadline_utc <= now)
            .options(selectinload(Event.guild_settings))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def activate_event(event_id: int) -> Event:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Event).where(Event.id == event_id)
        event = (await session.execute(stmt)).scalar_one_or_none()

        if not event:
            raise ValueError(f"Event {event_id} not found.")

        event.status = "active"
        await session.commit()
        await session.refresh(event)
        return event


async def end_event(event_id: int, submission_deadline_hours: int = 24) -> Event:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Event).where(Event.id == event_id)
        event = (await session.execute(stmt)).scalar_one_or_none()

        if not event:
            raise ValueError(f"Event {event_id} not found.")

        event.status = "submission_open"
        if event.submission_deadline_utc is None:
            event.submission_deadline_utc = event.end_time_utc + timedelta(
                hours=submission_deadline_hours
            )

        await session.commit()
        await session.refresh(event)
        return event


async def finalize_event(event_id: int) -> Event:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Event).where(Event.id == event_id)
        event = (await session.execute(stmt)).scalar_one_or_none()

        if not event:
            raise ValueError(f"Event {event_id} not found.")

        event.status = "finalized"
        await session.commit()
        await session.refresh(event)
        return event
