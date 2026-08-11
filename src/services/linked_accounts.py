"""Linked accounts CRUD service layer."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.engine import get_session_factory
from src.db.models import GuildMember, GuildSettings, LinkedAccount, User
from src.providers.codeforces import CodeforcesUser

logger = logging.getLogger("arena.services.linked_accounts")


async def link_account(
    guild_id: str,
    user_id: str,
    platform: str,
    handle: str,
    profile_url: str,
    validation_status: str = "pending",
    current_rating: int | None = None,
    max_rating: int | None = None,
    global_rank: int | None = None,
    extra_data: dict | None = None,
) -> LinkedAccount:
    """Create or update a linked account for a user in a guild.

    If an account for this platform already exists for the member, it is updated.
    Also ensures the user and guild_member rows exist, and marks the member
    as a verified competitor.

    Args:
        guild_id: Discord guild ID
        user_id: Discord user ID
        platform: The platform (e.g., "codeforces", "codechef", "leetcode")
        handle: The user's handle on the platform
        profile_url: Full URL to the user's profile
        validation_status: Verification status
        max_rating: Optional max rating
        global_rank: Optional global rank
        extra_data: Optional extra data dictionary
    """
    factory = get_session_factory()
    async with factory() as session:
        # 1. Ensure GuildSettings
        stmt_gs = select(GuildSettings).where(GuildSettings.discord_guild_id == guild_id)
        result_gs = await session.execute(stmt_gs)
        gs = result_gs.scalar_one_or_none()
        if gs is None:
            gs = GuildSettings(discord_guild_id=guild_id)
            session.add(gs)
            await session.flush()

        # 2. Ensure User
        stmt_u = select(User).where(User.discord_user_id == user_id)
        result_u = await session.execute(stmt_u)
        user = result_u.scalar_one_or_none()
        if user is None:
            user = User(discord_user_id=user_id)
            session.add(user)
            await session.flush()

        # 3. Ensure GuildMember
        stmt_gm = select(GuildMember).where(
            GuildMember.guild_settings_id == gs.id, GuildMember.user_id == user.id
        )
        result_gm = await session.execute(stmt_gm)
        member = result_gm.scalar_one_or_none()
        if member is None:
            member = GuildMember(guild_settings_id=gs.id, user_id=user.id)
            session.add(member)
            await session.flush()

        # 4. Check for existing linked account for this platform
        stmt_acc = select(LinkedAccount).where(
            LinkedAccount.guild_member_id == member.id, LinkedAccount.platform == platform
        )
        result_acc = await session.execute(stmt_acc)
        account = result_acc.scalar_one_or_none()

        normalized_handle = handle.lower()
        now = datetime.now(UTC)

        if account is None:
            account = LinkedAccount(
                guild_member_id=member.id,
                platform=platform,
                handle=handle,
                normalized_handle=normalized_handle,
                profile_url=profile_url,
                validation_status=validation_status,
                current_rating=current_rating,
                max_rating=max_rating,
                global_rank=global_rank,
                extra_data=extra_data,
                last_synced_at=now,
                last_sync_status="success" if validation_status == "validated" else None,
            )
            session.add(account)
        else:
            account.handle = handle
            account.normalized_handle = normalized_handle
            account.profile_url = profile_url
            account.validation_status = validation_status
            account.current_rating = current_rating
            account.max_rating = max_rating
            account.global_rank = global_rank
            account.extra_data = extra_data
            account.last_synced_at = now
            if validation_status == "validated":
                account.last_sync_status = "success"

        # Mark as verified competitor
        member.verified_competitor = True

        try:
            await session.commit()
            await session.refresh(account)
            logger.info(
                "Linked %s account %s for user %s in guild %s", platform, handle, user_id, guild_id
            )
            return account
        except IntegrityError as e:
            await session.rollback()
            raise ValueError(
                f"Could not link {platform} account (already exists or constraint failed)."
            ) from e


async def unlink_account(guild_id: str, user_id: str, platform: str) -> bool:
    """Remove a linked account for a platform.

    If no accounts remain, verified_competitor is set to False.
    Returns True if an account was removed, False if it didn't exist.
    """
    factory = get_session_factory()
    async with factory() as session:
        # Find the guild member
        stmt = (
            select(GuildMember)
            .join(GuildSettings)
            .join(User)
            .where(
                GuildSettings.discord_guild_id == guild_id,
                User.discord_user_id == user_id,
            )
        )
        result = await session.execute(stmt)
        member = result.scalar_one_or_none()

        if member is None:
            return False

        # Find the account
        stmt_acc = select(LinkedAccount).where(
            LinkedAccount.guild_member_id == member.id, LinkedAccount.platform == platform
        )
        result_acc = await session.execute(stmt_acc)
        account = result_acc.scalar_one_or_none()

        if account is None:
            return False

        await session.delete(account)
        await session.flush()

        # Check if any accounts remain for this member
        stmt_count = select(LinkedAccount).where(LinkedAccount.guild_member_id == member.id)
        result_count = await session.execute(stmt_count)
        remaining = result_count.scalars().all()

        if not remaining:
            member.verified_competitor = False

        await session.commit()
        logger.info("Unlinked %s account for user %s in guild %s", platform, user_id, guild_id)
        return True


async def get_member_accounts(guild_id: str, user_id: str) -> list[LinkedAccount]:
    """Get all linked accounts for a user in a guild."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(LinkedAccount)
            .join(GuildMember)
            .join(GuildSettings)
            .join(User)
            .where(
                GuildSettings.discord_guild_id == guild_id,
                User.discord_user_id == user_id,
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_account(guild_id: str, user_id: str, platform: str) -> LinkedAccount | None:
    """Get a specific linked account for a user in a guild."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(LinkedAccount)
            .join(GuildMember)
            .join(GuildSettings)
            .join(User)
            .where(
                GuildSettings.discord_guild_id == guild_id,
                User.discord_user_id == user_id,
                LinkedAccount.platform == platform,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
