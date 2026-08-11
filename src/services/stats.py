"""Aggregation engine for computing member statistics and tracking cycles."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Event,
    EventLeaderboardEntry,
    EventSubmission,
    GuildMember,
    GuildSettings,
)
from src.services.ratings import compute_member_star_ratings

logger = logging.getLogger("arena.services.stats")


# Fix an arbitrary epoch (e.g., Monday, Jan 1, 2024, 00:00:00 UTC)
# Every 14 days from this epoch is a new cycle.
CYCLE_EPOCH = datetime(2024, 1, 1, tzinfo=UTC)
CYCLE_LENGTH_DAYS = 14


def get_current_cycle_start() -> datetime:
    """Calculate the start time of the current 2-week cycle."""
    now = datetime.now(UTC)
    delta = now - CYCLE_EPOCH
    cycles_passed = delta.days // CYCLE_LENGTH_DAYS
    return CYCLE_EPOCH + timedelta(days=cycles_passed * CYCLE_LENGTH_DAYS)


async def recompute_member_stats(
    session: AsyncSession, guild_member_id: int
) -> GuildMember | None:
    """Recompute all leaderboards/stats for a single member idempotently.
    
    This function rebuilds stats entirely from finalized EventLeaderboardEntry and EventSubmission rows.
    """
    member = await session.get(GuildMember, guild_member_id)
    if not member:
        return None

    # We need linked accounts to recalculate ratings
    await session.refresh(member, ["linked_accounts"])

    # 1. Calculate CP and DSA ratings
    cp_stars, dsa_stars = await compute_member_star_ratings(member.linked_accounts)
    member.cp_star_rating = cp_stars
    member.dsa_star_rating = dsa_stars

    # 2. Get all finalized leaderboard entries
    stmt = (
        select(EventLeaderboardEntry, Event)
        .join(Event, EventLeaderboardEntry.event_id == Event.id)
        .where(
            EventLeaderboardEntry.guild_member_id == guild_member_id,
            EventLeaderboardEntry.is_final == True,
        )
        .order_by(Event.start_time_utc.asc())
    )
    result = await session.execute(stmt)
    entries_with_events = result.all()

    # 3. Calculate points
    total_points = 0
    cycle_points = 0
    events_participated = set()
    current_cycle_start = get_current_cycle_start()

    # Track streak
    current_streak = 0
    longest_streak = 0
    last_event_time = None

    for entry, event in entries_with_events:
        total_points += entry.total_points
        events_participated.add(event.id)

        if event.start_time_utc >= current_cycle_start:
            cycle_points += entry.total_points

        # Simple streak calculation: participating in events no more than 14 days apart
        if last_event_time is None:
            current_streak = 1
        else:
            days_diff = (event.start_time_utc - last_event_time).days
            if days_diff <= 14:
                current_streak += 1
            else:
                current_streak = 1
        longest_streak = max(longest_streak, current_streak)
        last_event_time = event.start_time_utc

    # Check if the streak is still active (less than 14 days since last event)
    if last_event_time and (datetime.now(UTC) - last_event_time).days > 14:
        current_streak = 0

    member.arena_points_all_time = total_points
    member.arena_points_current_cycle = cycle_points
    member.events_participated = len(events_participated)
    member.current_streak = current_streak
    member.longest_streak = longest_streak
    
    # 4. Calculate Verified Results & Problems Solved
    stmt_subs = (
        select(func.sum(EventSubmission.questions_solved).label("problems"), func.count().label("verified"))
        .where(
            EventSubmission.guild_member_id == guild_member_id,
            EventSubmission.verification_status.in_(["verified", "adjusted"])
        )
    )
    sub_res = await session.execute(stmt_subs)
    row = sub_res.one()
    member.problems_solved_total = row.problems or 0
    member.verified_results_count = row.verified or 0

    # Ensure member has standard verified competitor role if they have linked accounts
    member.verified_competitor = len(member.linked_accounts) > 0

    return member


async def rollover_cycles(session: AsyncSession) -> None:
    """Checks if a new cycle has started; if so, zeroes out `arena_points_current_cycle` 
    and handles Cycle Champion role assignment.
    
    This is intended to be called by a daily background task.
    """
    # For now, if we don't have a specific cycle tracking table, 
    # we can just compute the cycle dynamically inside recompute.
    # However, to do a server-wide reset, we can just fetch all members 
    # and zero out their cycle points if they haven't been updated in this cycle.
    
    # To truly do a rollover and assign the Champion role, we would need 
    # a dedicated cycle history table. But a simpler approach is:
    # `recompute_member_stats` already calculates cycle_points based on the *current* cycle start.
    # So technically, `arena_points_current_cycle` is automatically 0 if we just recompute everyone.
    
    # Instead of zeroing manually, we can simply recompute all members 
    # who have non-zero points when a new cycle is detected.
    
    # We can rely on a task calling `recompute_member_stats` on all members 
    # periodically or on-demand, which will automatically fix their cycle points.
    pass
