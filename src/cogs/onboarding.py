"""Onboarding cog — welcome messages and /start command."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.services import guild_settings as gs_service

logger = logging.getLogger("arena.cogs.onboarding")


class Onboarding(commands.Cog):
    """Welcome new members and guide them through setup."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── on_member_join listener ───────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Post a welcome message when a new member joins, if configured."""
        guild = member.guild

        settings = await gs_service.get_settings(str(guild.id))

        if settings is None or settings.onboarding_channel_id is None:
            logger.warning(
                "No onboarding channel configured for guild %s (%s) — skipping welcome",
                guild.name,
                guild.id,
            )
            return

        channel = guild.get_channel(int(settings.onboarding_channel_id))

        if channel is None:
            logger.warning(
                "Onboarding channel %s no longer exists in guild %s (%s)",
                settings.onboarding_channel_id,
                guild.name,
                guild.id,
            )
            return

        if not isinstance(channel, discord.abc.Messageable):
            logger.warning(
                "Onboarding channel %s in guild %s is not messageable",
                settings.onboarding_channel_id,
                guild.id,
            )
            return

        # Check we can actually send messages
        perms = channel.permissions_for(guild.me)
        if not perms.send_messages:
            logger.warning(
                "Cannot send messages in onboarding channel #%s (%s) in guild %s",
                channel.name,
                channel.id,
                guild.id,
            )
            return

        embed = discord.Embed(
            title=f"Welcome to {guild.name}! ⚔️",
            description=(
                f"Hey {member.mention}, welcome to **{guild.name}**!\n\n"
                f"We're a community of competitive programmers who sharpen their "
                f"skills together. Here's how to get started:\n\n"
                f"**1.** Use `/start` to see your next steps\n"
                f"**2.** Link your coding profiles (Codeforces, etc.)\n"
                f"**3.** Opt in to contest alert notifications\n\n"
                f"Good luck and happy coding! 🚀"
            ),
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        if guild.icon:
            embed.set_footer(text=guild.name, icon_url=guild.icon.url)

        try:
            await channel.send(embed=embed)
            logger.info(
                "Sent welcome message for %s in guild %s (#%s)",
                member,
                guild.id,
                channel.name,
            )
        except discord.Forbidden:
            logger.warning(
                "Forbidden sending welcome in #%s (%s) — guild %s",
                channel.name,
                channel.id,
                guild.id,
            )
        except discord.HTTPException:
            logger.exception(
                "HTTP error sending welcome in #%s (%s) — guild %s",
                channel.name,
                channel.id,
                guild.id,
            )

    # ── /start command ────────────────────────────────────────────────

    @app_commands.command(
        name="start",
        description="Get started with The Citadel — see your next steps",
    )
    @app_commands.guild_only()
    async def start(self, interaction: discord.Interaction) -> None:
        """Show an ephemeral onboarding guide for the member."""
        embed = discord.Embed(
            title="🏰 Welcome to The Citadel",
            description=("Here's how to make the most of your experience:\n"),
            color=discord.Color.teal(),
        )

        embed.add_field(
            name="🔗 Link Your Profiles",
            value=(
                "Use `/link-codeforces` to connect your Codeforces account. "
                "The community will be able to see your progress!\n"
                "*(Support for other platforms coming soon)*"
            ),
            inline=False,
        )

        embed.add_field(
            name="🔔 Contest Alerts",
            value=(
                "Opt in to get notified before upcoming contests "
                "so you never miss a round.\n"
                "*Coming soon — stay tuned!*"
            ),
            inline=False,
        )

        embed.add_field(
            name="📅 Upcoming Contests",
            value=(
                "Check what contests are happening soon across "
                "Codeforces and other platforms.\n"
                "*Coming soon — stay tuned!*"
            ),
            inline=False,
        )

        embed.set_footer(text="More features are being built — watch this space!")

        logger.info("/start used by %s in guild %s", interaction.user, interaction.guild_id)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Load the Onboarding cog."""
    await bot.add_cog(Onboarding(bot))
    logger.info("Onboarding cog loaded")
