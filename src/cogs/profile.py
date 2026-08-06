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

    # ── /link-codeforces ──────────────────────────────────────────────

    @app_commands.command(
        name="link-codeforces",
        description="Link your Codeforces account to your profile",
    )
    @app_commands.describe(handle="Your exact Codeforces handle")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 30.0, key=lambda i: (i.guild_id, i.user.id))
    async def link_codeforces(self, interaction: discord.Interaction, handle: str) -> None:
        """Link a Codeforces account."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        logger.info(
            "%s is attempting to link Codeforces handle %r in guild %s",
            interaction.user,
            handle,
            interaction.guild.id,
        )

        cf_user = await fetch_user(handle)
        if cf_user is None:
            await interaction.followup.send(
                f"❌ **Link failed**: Could not find a Codeforces user with handle `{handle}`. "
                f"Please check the spelling and try again.",
                ephemeral=True,
            )
            return

        try:
            account = await la_service.link_account(
                str(interaction.guild.id),
                str(interaction.user.id),
                "codeforces",
                cf_user.handle,
                cf_user,
            )
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
            title="✅ Codeforces Account Linked",
            description=f"Successfully linked **{account.handle}** to your profile.",
            color=discord.Color.green(),
            url=account.profile_url,
        )
        if cf_user.rating:
            embed.add_field(
                name="Rating", value=f"{cf_user.rating} (Max: {cf_user.max_rating})", inline=True
            )
        if cf_user.rank:
            embed.add_field(name="Rank", value=cf_user.rank.title(), inline=True)

        if cf_user.avatar:
            embed.set_thumbnail(url=cf_user.avatar)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @link_codeforces.error
    async def link_codeforces_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Handle errors for /link-codeforces."""
        if isinstance(error, app_commands.CommandOnCooldown):
            # If the command wasn't deferred yet, we must respond
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
            if acc.current_rating is not None:
                val += f"**Rating:** {acc.current_rating}\n"
            if acc.max_rating is not None:
                val += f"**Max Rating:** {acc.max_rating}\n"

            # Show last synced time if available
            if acc.last_synced_at:
                val += f"*(Last synced: <t:{int(acc.last_synced_at.timestamp())}:R>)*"

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
