"""Profile cog — manage linked competitive programming accounts."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.providers.codeforces import fetch_user
from src.services import linked_accounts as la_service

logger = logging.getLogger("arena.cogs.profile")


class Profile(commands.Cog):
    """Manage and view linked competitive programming profiles."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /link ─────────────────────────────────────────────────────────

    def _extract_handle(self, handle_or_url: str) -> str:
        handle_or_url = handle_or_url.strip().rstrip("/")
        if "/" in handle_or_url:
            return handle_or_url.split("/")[-1]
        return handle_or_url

    @app_commands.command(
        name="link",
        description="Link a competitive programming account to your profile",
    )
    @app_commands.describe(
        platform="The platform to link",
        handle="Your handle or profile URL"
    )
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="Codeforces", value="codeforces"),
            app_commands.Choice(name="CodeChef", value="codechef"),
            app_commands.Choice(name="LeetCode", value="leetcode"),
        ]
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: (i.guild_id, i.user.id))
    async def link(self, interaction: discord.Interaction, platform: str, handle: str) -> None:
        """Link a competitive programming account."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        
        handle = self._extract_handle(handle)

        logger.info(
            "%s is attempting to link %s handle %r in guild %s",
            interaction.user,
            platform,
            handle,
            interaction.guild.id,
        )

        validation_status = "unverified"
        current_rating = None
        max_rating = None
        global_rank = None
        extra_data = {}
        profile_url = ""

        if platform == "codeforces":
            cf_user = await fetch_user(handle)
            if cf_user is None:
                await interaction.followup.send(
                    f"❌ **Link failed**: Could not find a Codeforces user with handle `{handle}`.",
                    ephemeral=True,
                )
                return
            handle = cf_user.handle
            current_rating = cf_user.rating
            max_rating = cf_user.max_rating
            validation_status = "validated"
            profile_url = f"https://codeforces.com/profile/{handle}"
            
        elif platform == "codechef":
            from src.providers.codechef import fetch_user as cc_fetch
            cc_user = await cc_fetch(handle)
            if cc_user is None:
                await interaction.followup.send(
                    f"❌ **Link failed**: Could not fetch CodeChef user `{handle}`.",
                    ephemeral=True,
                )
                return
            current_rating = cc_user.rating
            max_rating = cc_user.max_rating
            if cc_user.stars is not None:
                extra_data["stars"] = cc_user.stars
            validation_status = "validated"
            profile_url = f"https://www.codechef.com/users/{handle}"
            
        elif platform == "leetcode":
            from src.providers.leetcode import fetch_user_stats as lc_fetch
            lc_user = await lc_fetch(handle)
            # We use the fetch to at least verify the account exists. It also brings the rating.
            if lc_user is None:
                await interaction.followup.send(
                    f"❌ **Link failed**: Could not find LeetCode user `{handle}`.",
                    ephemeral=True,
                )
                return
            current_rating = lc_user.rating
            max_rating = lc_user.rating
            global_rank = lc_user.global_rank
            extra_data["easy_solved"] = lc_user.easy_solved
            extra_data["medium_solved"] = lc_user.medium_solved
            extra_data["hard_solved"] = lc_user.hard_solved
            validation_status = "validated" # Assume validated
            profile_url = f"https://leetcode.com/u/{handle}/"

        try:
            account = await la_service.link_account(
                guild_id=str(interaction.guild.id),
                user_id=str(interaction.user.id),
                platform=platform,
                handle=handle,
                profile_url=profile_url,
                validation_status=validation_status,
                current_rating=current_rating,
                max_rating=max_rating,
                global_rank=global_rank,
                extra_data=extra_data if extra_data else None,
            )
            
            # Sync roles after linking
            from src.db.engine import get_session_factory
            from src.db.models import GuildSettings, User, GuildMember
            from sqlalchemy import select
            from src.services.stats import recompute_member_stats
            
            factory = get_session_factory()
            async with factory() as session:
                # Need to find the member ID
                stmt = select(GuildMember.id).join(User).join(GuildSettings).where(
                    GuildSettings.discord_guild_id == str(interaction.guild.id),
                    User.discord_user_id == str(interaction.user.id)
                )
                member_id = await session.scalar(stmt)
                if member_id:
                    await recompute_member_stats(session, member_id)
                    await session.commit()
            
        except ValueError as e:
            await interaction.followup.send(f"❌ **Error**: {e}", ephemeral=True)
            return
        except Exception:
            logger.exception("Unexpected error linking account")
            await interaction.followup.send(
                "❌ **Error**: An unexpected error occurred while linking your account. Please try again later.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"✅ {platform.title()} Account Linked",
            description=f"Successfully linked **{account.handle}** to your profile.",
            color=discord.Color.green(),
            url=account.profile_url,
        )
        if current_rating:
            embed.add_field(
                name="Rating", value=f"{current_rating}" + (f" (Max: {max_rating})" if max_rating else ""), inline=True
            )
        if validation_status == "unverified":
            embed.set_footer(text="Status: Unverified")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="link-codeforces",
        description="Alias for /link platform:Codeforces",
    )
    @app_commands.describe(handle="Your exact Codeforces handle")
    @app_commands.guild_only()
    async def link_codeforces(self, interaction: discord.Interaction, handle: str) -> None:
        """Alias for linking Codeforces."""
        await self.link.callback(self, interaction, platform="codeforces", handle=handle)

    @link.error
    async def link_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Handle errors for /link."""
        if isinstance(error, app_commands.CommandOnCooldown):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"⏳ You are on cooldown. Please try again in {error.retry_after:.1f} seconds.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"⏳ You are on cooldown. Please try again in {error.retry_after:.1f} seconds.",
                    ephemeral=True,
                )

    # ── /unlink ───────────────────────────────────────────────────────

    @app_commands.command(
        name="unlink",
        description="Unlink a competitive programming account",
    )
    @app_commands.describe(platform="The platform to unlink")
    @app_commands.choices(
        platform=[
            app_commands.Choice(name="Codeforces", value="codeforces"),
            app_commands.Choice(name="CodeChef", value="codechef"),
            app_commands.Choice(name="LeetCode", value="leetcode"),
        ]
    )
    @app_commands.guild_only()
    async def unlink(self, interaction: discord.Interaction, platform: str) -> None:
        """Unlink an account for a specific platform."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        success = await la_service.unlink_account(
            str(interaction.guild.id), str(interaction.user.id), platform
        )

        if success:
            # Sync roles after unlinking
            from src.db.engine import get_session_factory
            from src.db.models import GuildSettings, User, GuildMember
            from sqlalchemy import select
            from src.services.stats import recompute_member_stats
            
            factory = get_session_factory()
            async with factory() as session:
                # Need to find the member ID
                stmt = select(GuildMember.id).join(User).join(GuildSettings).where(
                    GuildSettings.discord_guild_id == str(interaction.guild.id),
                    User.discord_user_id == str(interaction.user.id)
                )
                member_id = await session.scalar(stmt)
                if member_id:
                    await recompute_member_stats(session, member_id)
                    await session.commit()
                    
            await interaction.followup.send(
                f"✅ Your **{platform.title()}** account has been unlinked.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"❌ You don't have a linked **{platform.title()}** account in this server.",
                ephemeral=True,
            )

    # ── /my-profile ───────────────────────────────────────────────────

    @app_commands.command(
        name="my-profile",
        description="View your linked competitive programming accounts",
    )
    @app_commands.guild_only()
    async def my_profile(self, interaction: discord.Interaction) -> None:
        """Show the invoking user's linked accounts (ephemeral)."""
        await self._show_profile(interaction, interaction.user, ephemeral=True)

    # ── /profile ──────────────────────────────────────────────────────

    @app_commands.command(
        name="profile",
        description="View another member's linked competitive programming accounts",
    )
    @app_commands.describe(member="The server member to view")
    @app_commands.guild_only()
    async def profile(self, interaction: discord.Interaction, member: discord.Member) -> None:
        """Show another user's linked accounts (public)."""
        await self._show_profile(interaction, member, ephemeral=False)

    # ── Shared Profile Logic ──────────────────────────────────────────

    async def _show_profile(
        self,
        interaction: discord.Interaction,
        target: discord.Member | discord.User,
        ephemeral: bool,
    ) -> None:
        """Fetch and display linked accounts for a user."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=ephemeral)

        accounts = await la_service.get_member_accounts(str(interaction.guild.id), str(target.id))

        embed = discord.Embed(
            title=f"🏆 Profiles for {target.display_name}",
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        if not accounts:
            embed.description = "No linked accounts found."
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            return

        for acc in accounts:
            val = f"**Handle:** [{acc.handle}]({acc.profile_url})\n"
            val += f"**Status:** {'✅ Verified' if acc.validation_status == 'validated' else '⚠️ Unverified'}\n"
            if acc.current_rating is not None:
                val += f"**Rating:** {acc.current_rating}\n"
            if acc.max_rating is not None:
                val += f"**Max Rating:** {acc.max_rating}\n"

            if acc.platform == "codechef" and acc.extra_data and "stars" in acc.extra_data:
                val += f"**Stars:** {acc.extra_data['stars']}★\n"
            
            if acc.platform == "leetcode" and acc.extra_data:
                if acc.global_rank:
                    val += f"**Rank:** {acc.global_rank:,}\n"
                easy = acc.extra_data.get('easy_solved', 0)
                med = acc.extra_data.get('medium_solved', 0)
                hard = acc.extra_data.get('hard_solved', 0)
                if easy or med or hard:
                    val += f"**Problems Solved:** {easy} Easy, {med} Medium, {hard} Hard\n"

            # Show last synced time if available
            if acc.last_synced_at:
                val += f"*(Last synced: <t:{int(acc.last_synced_at.timestamp())}:R>)*\n"

            embed.add_field(
                name=f"{acc.platform.title()}",
                value=val,
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=ephemeral)


async def setup(bot: commands.Bot) -> None:
    """Load the Profile cog."""
    await bot.add_cog(Profile(bot))
    logger.info("Profile cog loaded")
