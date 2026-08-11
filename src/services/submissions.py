"""Event submissions CRUD service layer.

All functions acquire their own AsyncSession, commit, and close — keeping the
service stateless and safe for concurrent Discord events.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.db.engine import get_session_factory
from src.db.models import Event, EventSubmission, GuildMember, GuildSettings, User

logger = logging.getLogger("arena.services.submissions")


async def create_or_update_submission(
    event_id: int,
    guild_id: str,
    user_id: str,
    questions_solved: int,
    *,
    claimed_rank: int | None = None,
    claimed_rating_before: int | None = None,
    claimed_rating_after: int | None = None,
    evidence_url: str | None = None,
    reflection: str | None = None,
) -> EventSubmission:
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(Event)
            .join(GuildSettings, Event.guild_settings_id == GuildSettings.id)
            .where(Event.id == event_id, GuildSettings.discord_guild_id == guild_id)
        )
        event = (await session.execute(stmt)).scalar_one_or_none()

        if not event:
            raise ValueError("Event not found or does not belong to this guild.")

        if event.status != "submission_open":
            raise ValueError(f"Event status is '{event.status}', not 'submission_open'.")

        now = datetime.now(UTC)
        if event.submission_deadline_utc and event.submission_deadline_utc < now:
            raise ValueError("Submission deadline has passed.")

        # Ensure user exists
        stmt_user = select(User).where(User.discord_user_id == user_id)
        user = (await session.execute(stmt_user)).scalar_one_or_none()
        if not user:
            user = User(discord_user_id=user_id)
            session.add(user)
            await session.flush()

        # Ensure guild member exists
        stmt_member = select(GuildMember).where(
            GuildMember.user_id == user.id, GuildMember.guild_settings_id == event.guild_settings_id
        )
        member = (await session.execute(stmt_member)).scalar_one_or_none()
        if not member:
            member = GuildMember(user_id=user.id, guild_settings_id=event.guild_settings_id)
            session.add(member)
            await session.flush()

        claimed_rating_change = None
        if claimed_rating_before is not None and claimed_rating_after is not None:
            claimed_rating_change = claimed_rating_after - claimed_rating_before

        verification_status = "pending" if event.results_require_moderator_approval else "verified"

        # Check for existing submission
        stmt_sub = select(EventSubmission).where(
            EventSubmission.event_id == event_id, EventSubmission.guild_member_id == member.id
        )
        submission = (await session.execute(stmt_sub)).scalar_one_or_none()

        if submission:
            submission.questions_solved = questions_solved
            submission.claimed_rank = claimed_rank
            submission.claimed_rating_before = claimed_rating_before
            submission.claimed_rating_after = claimed_rating_after
            submission.claimed_rating_change = claimed_rating_change
            submission.evidence_url = evidence_url
            submission.reflection = reflection
            submission.verification_status = verification_status
            submission.updated_at = datetime.now(UTC)
            submission.verified_by_discord_user_id = None
            submission.verified_at = None
            submission.moderator_note = None
        else:
            submission = EventSubmission(
                event_id=event_id,
                guild_member_id=member.id,
                questions_solved=questions_solved,
                claimed_rank=claimed_rank,
                claimed_rating_before=claimed_rating_before,
                claimed_rating_after=claimed_rating_after,
                claimed_rating_change=claimed_rating_change,
                evidence_url=evidence_url,
                reflection=reflection,
                verification_status=verification_status,
            )
            session.add(submission)

        await session.commit()
        await session.refresh(submission)
        return submission


async def get_submission(submission_id: int) -> EventSubmission | None:
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(EventSubmission)
            .options(
                selectinload(EventSubmission.guild_member).selectinload(GuildMember.user),
                selectinload(EventSubmission.event),
            )
            .where(EventSubmission.id == submission_id)
        )
        return (await session.execute(stmt)).scalar_one_or_none()


async def get_submission_by_member(
    event_id: int, guild_id: str, user_id: str
) -> EventSubmission | None:
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(EventSubmission)
            .join(GuildMember, EventSubmission.guild_member_id == GuildMember.id)
            .join(User, GuildMember.user_id == User.id)
            .join(Event, EventSubmission.event_id == Event.id)
            .join(GuildSettings, Event.guild_settings_id == GuildSettings.id)
            .where(
                EventSubmission.event_id == event_id,
                GuildSettings.discord_guild_id == guild_id,
                User.discord_user_id == user_id,
            )
            .options(
                selectinload(EventSubmission.guild_member).selectinload(GuildMember.user),
                selectinload(EventSubmission.event),
            )
        )
        return (await session.execute(stmt)).scalar_one_or_none()


async def list_submissions(
    event_id: int, guild_id: str, *, status: str | None = None
) -> list[EventSubmission]:
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(EventSubmission)
            .join(Event, EventSubmission.event_id == Event.id)
            .join(GuildSettings, Event.guild_settings_id == GuildSettings.id)
            .where(EventSubmission.event_id == event_id, GuildSettings.discord_guild_id == guild_id)
            .options(
                selectinload(EventSubmission.guild_member).selectinload(GuildMember.user),
                selectinload(EventSubmission.event),
            )
        )
        if status:
            stmt = stmt.where(EventSubmission.verification_status == status)

        result = await session.execute(stmt)
        return list(result.scalars().all())


async def approve_submission(
    submission_id: int, verified_by: str, *, note: str | None = None
) -> EventSubmission:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(EventSubmission).where(EventSubmission.id == submission_id)
        submission = (await session.execute(stmt)).scalar_one_or_none()

        if not submission:
            raise ValueError("Submission not found.")
        if submission.verification_status != "pending":
            raise ValueError("Submission is not pending.")

        submission.verification_status = "verified"
        submission.verified_by_discord_user_id = verified_by
        submission.verified_at = datetime.now(UTC)
        submission.moderator_note = note

        await session.commit()
        await session.refresh(submission)
        return submission


async def reject_submission(submission_id: int, verified_by: str, reason: str) -> EventSubmission:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(EventSubmission).where(EventSubmission.id == submission_id)
        submission = (await session.execute(stmt)).scalar_one_or_none()

        if not submission:
            raise ValueError("Submission not found.")
        if submission.verification_status != "pending":
            raise ValueError("Submission is not pending.")

        submission.verification_status = "rejected"
        submission.verified_by_discord_user_id = verified_by
        submission.verified_at = datetime.now(UTC)
        submission.moderator_note = reason

        await session.commit()
        await session.refresh(submission)
        return submission
