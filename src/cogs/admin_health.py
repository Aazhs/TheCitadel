"""Admin health-check cog with /system-db-status command."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.services.db_health import check_db_health

logger = logging.getLogger("arena.cogs.admin_health")


class AdminHealth(commands.Cog):
    """Admin-only diagnostic commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="system-db-status",
        description="[Admin] Check database connectivity",
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def system_db_status(self, interaction: discord.Interaction) -> None:
        """Test database connectivity and return a concise ephemeral result."""
        await interaction.response.defer(ephemeral=True)

        result = await check_db_health()

        if result.healthy:
            embed = discord.Embed(
                title="✅ Database Online",
                color=discord.Color.green(),
            )
            embed.add_field(name="Latency", value=f"{result.latency_ms}ms", inline=True)
            embed.add_field(name="Server", value=result.server_version[:80], inline=False)
        else:
            embed = discord.Embed(
                title="❌ Database Offline",
                color=discord.Color.red(),
            )
            embed.add_field(name="Latency", value=f"{result.latency_ms}ms", inline=True)
            # Show error class only — never expose full connection details
            error_summary = result.error or "Unknown error"
            if len(error_summary) > 200:
                error_summary = error_summary[:200] + "…"
            embed.add_field(name="Error", value=f"```{error_summary}```", inline=False)

        logger.info(
            "system-db-status by %s — healthy=%s latency=%.1fms",
            interaction.user,
            result.healthy,
            result.latency_ms,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @system_db_status.error
    async def system_db_status_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Handle permission errors for the db-status command."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "⛔ You need **Administrator** permission to use this command.",
                ephemeral=True,
            )
        else:
            logger.exception("Unexpected error in system-db-status: %s", error)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An unexpected error occurred.", ephemeral=True
                )


async def setup(bot: commands.Bot) -> None:
    """Load the AdminHealth cog."""
    await bot.add_cog(AdminHealth(bot))
    logger.info("AdminHealth cog loaded")
