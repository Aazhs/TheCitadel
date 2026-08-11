"""Contests service for syncing and querying external contests."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from src.db.engine import get_session_factory
from src.db.models import Contest
from src.providers.codeforces import CodeforcesContest

logger = logging.getLogger("arena.services.contests")


async def sync_codeforces_contests(cf_contests: list[CodeforcesContest]) -> tuple[int, int]:
    """Sync a list of codeforces contests to the database.

    Filters out finished contests that are older than 7 days to save DB writes.
    Performs an upsert on external_contest_id + platform.

    Returns:
        Tuple of (added_count, updated_count).
    """
    added_count = 0
    updated_count = 0

    now = datetime.now(UTC)
    seven_days_ago = now - timedelta(days=7)

    # Filter contests
    relevant_contests = []
    for c in cf_contests:
        start_time = None
        if c.start_time_seconds:
            start_time = datetime.fromtimestamp(c.start_time_seconds, tz=UTC)
        else:
            # Codeforces rarely does this, but default to now if missing start time
            start_time = now

        # Only sync if not finished OR if it finished within the last 7 days
        if c.phase != "FINISHED" or start_time > seven_days_ago:
            relevant_contests.append(
                {
                    "platform": "codeforces",
                    "external_contest_id": str(c.id),
                    "name": c.name,
                    "url": f"https://codeforces.com/contest/{c.id}",
                    "start_time_utc": start_time,
                    "duration_seconds": c.duration_seconds,
                    "phase": c.phase,
                    "updated_at": now,
                }
            )

    if not relevant_contests:
        return 0, 0

    async with get_session_factory()() as session:
        # 1. Fetch existing by platform + ids
        external_ids = [c["external_contest_id"] for c in relevant_contests]
        stmt = select(Contest).where(
            Contest.platform == "codeforces", Contest.external_contest_id.in_(external_ids)
        )
        result = await session.execute(stmt)
        existing_contests = {c.external_contest_id: c for c in result.scalars().all()}

        for c_data in relevant_contests:
            ext_id = c_data["external_contest_id"]
            if ext_id in existing_contests:
                existing = existing_contests[ext_id]
                # Check if we need to update
                if (
                    existing.phase != c_data["phase"]
                    or existing.start_time_utc != c_data["start_time_utc"]
                    or existing.name != c_data["name"]
                ):
                    existing.phase = c_data["phase"]
                    existing.start_time_utc = c_data["start_time_utc"]
                    existing.name = c_data["name"]
                    existing.duration_seconds = c_data["duration_seconds"]
                    existing.url = c_data["url"]
                    updated_count += 1
            else:
                new_contest = Contest(
                    platform=c_data["platform"],
                    external_contest_id=c_data["external_contest_id"],
                    name=c_data["name"],
                    url=c_data["url"],
                    start_time_utc=c_data["start_time_utc"],
                    duration_seconds=c_data["duration_seconds"],
                    phase=c_data["phase"],
                )
                session.add(new_contest)
                added_count += 1

        await session.commit()

    return added_count, updated_count

async def sync_codechef_contests(cc_contests: list) -> tuple[int, int]:
    """Sync CodeChef contests to the database."""
    from src.providers.codechef import CodeChefContest
    added_count = 0
    updated_count = 0
    now = datetime.now(UTC)
    seven_days_ago = now - timedelta(days=7)
    
    relevant_contests = []
    for c in cc_contests:
        if c.end_time_utc > seven_days_ago:
            phase = "BEFORE" if c.start_time_utc > now else "CODING" if c.end_time_utc > now else "FINISHED"
            relevant_contests.append({
                "platform": "codechef",
                "external_contest_id": c.code,
                "name": c.name,
                "url": f"https://www.codechef.com/{c.code}",
                "start_time_utc": c.start_time_utc,
                "duration_seconds": c.duration_minutes * 60,
                "phase": phase,
                "updated_at": now,
            })
            
    if not relevant_contests:
        return 0, 0
        
    async with get_session_factory()() as session:
        external_ids = [c["external_contest_id"] for c in relevant_contests]
        stmt = select(Contest).where(Contest.platform == "codechef", Contest.external_contest_id.in_(external_ids))
        result = await session.execute(stmt)
        existing_contests = {c.external_contest_id: c for c in result.scalars().all()}
        
        for c_data in relevant_contests:
            ext_id = c_data["external_contest_id"]
            if ext_id in existing_contests:
                existing = existing_contests[ext_id]
                if (existing.phase != c_data["phase"] or existing.start_time_utc != c_data["start_time_utc"] or existing.name != c_data["name"]):
                    existing.phase = c_data["phase"]
                    existing.start_time_utc = c_data["start_time_utc"]
                    existing.name = c_data["name"]
                    existing.duration_seconds = c_data["duration_seconds"]
                    existing.url = c_data["url"]
                    updated_count += 1
            else:
                session.add(Contest(**c_data))
                added_count += 1
        await session.commit()
    return added_count, updated_count

async def sync_leetcode_contests(lc_contests: list) -> tuple[int, int]:
    """Sync LeetCode contests to the database."""
    from src.providers.leetcode import LeetCodeContest
    added_count = 0
    updated_count = 0
    now = datetime.now(UTC)
    seven_days_ago = now - timedelta(days=7)
    
    relevant_contests = []
    for c in lc_contests:
        start_dt = datetime.fromtimestamp(c.start_time_utc, tz=UTC)
        end_dt = start_dt + timedelta(seconds=c.duration_seconds)
        if end_dt > seven_days_ago:
            phase = "BEFORE" if start_dt > now else "CODING" if end_dt > now else "FINISHED"
            relevant_contests.append({
                "platform": "leetcode",
                "external_contest_id": c.title_slug,
                "name": c.title,
                "url": f"https://leetcode.com/contest/{c.title_slug}",
                "start_time_utc": start_dt,
                "duration_seconds": c.duration_seconds,
                "phase": phase,
                "updated_at": now,
            })
            
    if not relevant_contests:
        return 0, 0
        
    async with get_session_factory()() as session:
        external_ids = [c["external_contest_id"] for c in relevant_contests]
        stmt = select(Contest).where(Contest.platform == "leetcode", Contest.external_contest_id.in_(external_ids))
        result = await session.execute(stmt)
        existing_contests = {c.external_contest_id: c for c in result.scalars().all()}
        
        for c_data in relevant_contests:
            ext_id = c_data["external_contest_id"]
            if ext_id in existing_contests:
                existing = existing_contests[ext_id]
                if (existing.phase != c_data["phase"] or existing.start_time_utc != c_data["start_time_utc"] or existing.name != c_data["name"]):
                    existing.phase = c_data["phase"]
                    existing.start_time_utc = c_data["start_time_utc"]
                    existing.name = c_data["name"]
                    existing.duration_seconds = c_data["duration_seconds"]
                    existing.url = c_data["url"]
                    updated_count += 1
            else:
                session.add(Contest(**c_data))
                added_count += 1
        await session.commit()
    return added_count, updated_count


async def get_upcoming_contests(limit: int = 5) -> list[Contest]:
    """Get the next N upcoming contests across all platforms.

    Returns:
        List of upcoming contests ordered by start time.
    """
    now = datetime.now(UTC)

    async with get_session_factory()() as session:
        stmt = (
            select(Contest)
            .where(Contest.start_time_utc > now)
            .order_by(Contest.start_time_utc.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
