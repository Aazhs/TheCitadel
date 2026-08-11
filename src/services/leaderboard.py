"""Leaderboard computation, persistence, and finalization service.

All functions acquire their own AsyncSession, commit, and close — keeping the
service stateless and safe for concurrent Discord events.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from src.db.engine import get_session_factory
from src.db.models import Event, EventLeaderboardEntry, EventSubmission, GuildMember, GuildSettings, User
from src.services import scoring

logger = logging.getLogger("arena.services.leaderboard")

async def compute_leaderboard(event_id: int) -> list[EventLeaderboardEntry]:
    """
    Computes and ranks the leaderboard for a specific event.
    Recreates all EventLeaderboardEntry rows for the event.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        event = await session.scalar(
            select(Event)
            .options(selectinload(Event.guild_settings))
            .where(Event.id == event_id)
        )
        if not event:
            raise ValueError(f"Event {event_id} not found")

        config = scoring.get_effective_config(event.points_config)

        submissions = (await session.scalars(
            select(EventSubmission)
            .options(
                selectinload(EventSubmission.guild_member).selectinload(GuildMember.user)
            )
            .where(
                EventSubmission.event_id == event_id,
                EventSubmission.verification_status.in_(("verified", "adjusted")),
            )
        )).all()

        entry_dicts = []
        for sub in submissions:
            sub_data = {
                "questions_solved": sub.questions_solved,
                "claimed_rating_before": sub.claimed_rating_before,
                "claimed_rating_after": sub.claimed_rating_after,
                "claimed_rank": sub.claimed_rank,
            }
            total, breakdown = scoring.compute_score(sub_data, config)
            sub.points_awarded = total
            sub.score_breakdown = breakdown

            rating_gain = 0
            if sub.claimed_rating_before is not None and sub.claimed_rating_after is not None:
                rating_gain = max(0, sub.claimed_rating_after - sub.claimed_rating_before)

            entry_dicts.append({
                "guild_member_id": sub.guild_member_id,
                "total_points": total,
                "questions_solved": sub.questions_solved,
                "rating_gain": rating_gain,
                "submitted_at": sub.submitted_at,
                "discord_user_id": sub.guild_member.user.discord_user_id,
                "score_breakdown": breakdown,
            })

        ranked = scoring.rank_entries(entry_dicts)

        await session.execute(
            delete(EventLeaderboardEntry).where(EventLeaderboardEntry.event_id == event_id)
        )

        new_entries = []
        for entry in ranked:
            lb_entry = EventLeaderboardEntry(
                event_id=event_id,
                guild_member_id=entry["guild_member_id"],
                rank=entry["rank"],
                total_points=entry["total_points"],
                score_breakdown=entry["score_breakdown"],
            )
            session.add(lb_entry)
            new_entries.append(lb_entry)
            
        await session.commit()
        return new_entries


async def get_leaderboard(event_id: int, *, limit: int = 10) -> list[EventLeaderboardEntry]:
    """
    Fetches the leaderboard for an event.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = (
            select(EventLeaderboardEntry)
            .where(EventLeaderboardEntry.event_id == event_id)
            .order_by(EventLeaderboardEntry.rank.asc())
            .limit(limit)
            .options(
                selectinload(EventLeaderboardEntry.guild_member).selectinload(GuildMember.user)
            )
        )
        entries = (await session.scalars(stmt)).all()
        return list(entries)


async def finalize_leaderboard(event_id: int, force: bool = False) -> list[EventLeaderboardEntry]:
    """
    Finalizes the leaderboard for an event, setting is_final=True on entries and marking the event as completed.
    """
    await compute_leaderboard(event_id)

    session_factory = get_session_factory()
    async with session_factory() as session:
        event = await session.scalar(
            select(Event).where(Event.id == event_id)
        )
        if not event:
            raise ValueError(f"Event {event_id} not found")

        if not force and event.status not in ("submission_closed", "completed"):
            raise ValueError("Cannot finalize while submissions are open. Close submissions first.")

        entries = (await session.scalars(
            select(EventLeaderboardEntry)
            .where(EventLeaderboardEntry.event_id == event_id)
        )).all()

        now = datetime.now(UTC)
        for entry in entries:
            entry.is_final = True
            entry.computed_at = now

        if event.status != "completed":
            event.status = "completed"

        await session.commit()
        
        # Trigger member stats recomputation after finalizing
        from src.services.stats import recompute_member_stats
        for entry in entries:
            await recompute_member_stats(session, entry.guild_member_id)
        await session.commit()
        
        return list(entries)


async def set_scoring_config(event_id: int, guild_id: str, overrides: dict) -> Event:
    """
    Sets the scoring config overrides for a specific event.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = (
            select(Event)
            .join(Event.guild_settings)
            .where(
                Event.id == event_id,
                GuildSettings.discord_guild_id == guild_id
            )
        )
        event = await session.scalar(stmt)
        if not event:
            raise ValueError(f"Event {event_id} for guild {guild_id} not found")

        scoring.validate_config(overrides)

        event.points_config = overrides
        await session.commit()
        await session.refresh(event)
        
        return event
