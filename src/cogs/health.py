"""Health-check cog with /ping command."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("arena.cogs.health")


class Health(commands.Cog):
    """Basic health-check commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check if the bot is online and responsive")
    async def ping(self, interaction: discord.Interaction) -> None:
        """Respond with the bot's current WebSocket latency."""
        latency_ms = round(self.bot.latency * 1000, 1)
        logger.info("Ping requested by %s — latency=%.1fms", interaction.user, latency_ms)
        await interaction.response.send_message(
            f"\U0001f3d3 **Pong!** Bot is online — latency: **{latency_ms}ms**",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    """Load the Health cog."""
    await bot.add_cog(Health(bot))
    logger.info("Health cog loaded")
