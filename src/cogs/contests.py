"""Contests cog for The Citadel."""

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.providers import codeforces as cf_provider
from src.services import contests as contest_service

logger = logging.getLogger("arena.cogs.contests")


class Contests(commands.Cog):
    """Cog for contest discovery and syncing."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._sync_task_started = False

    async def cog_load(self) -> None:
        """Start background tasks when cog is loaded."""
        if not self._sync_task_started:
            self.sync_contests_loop.start()
            self._sync_task_started = True

    async def cog_unload(self) -> None:
        """Cancel background tasks when cog is unloaded."""
        self.sync_contests_loop.cancel()
        self._sync_task_started = False

    @tasks.loop(hours=6)
    async def sync_contests_loop(self) -> None:
        """Background task to sync Codeforces contests every 6 hours."""
        logger.info("Starting scheduled Codeforces contest sync...")
        try:
            cf_contests = await cf_provider.fetch_contests()
            if cf_contests:
                added, updated = await contest_service.sync_codeforces_contests(cf_contests)
                logger.info("Scheduled sync complete: %d added, %d updated", added, updated)
            else:
                logger.warning("Scheduled sync fetched no contests or failed.")
        except Exception as e:
            logger.exception("Error during scheduled contest sync: %s", e)

    @sync_contests_loop.before_loop
    async def before_sync_contests(self) -> None:
        """Wait for the bot to be ready before starting the loop."""
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="upcoming",
        description="View upcoming Codeforces contests",
    )
    async def upcoming(self, interaction: discord.Interaction) -> None:
        """Show the next 5 upcoming contests."""
        await interaction.response.defer(ephemeral=False)

        upcoming = await contest_service.get_upcoming_contests(limit=5)

        if not upcoming:
            await interaction.followup.send(
                "No upcoming contests found. They might not be scheduled yet or the bot hasn't synced."
            )
            return

        embed = discord.Embed(
            title="Upcoming Contests",
            color=discord.Color.blue(),
        )

        for contest in upcoming:
            # Parse division from name if possible
            div_info = ""
            if "Div. 1" in contest.name:
                div_info = "[Div. 1] "
            elif "Div. 2" in contest.name:
                div_info = "[Div. 2] "
            elif "Div. 3" in contest.name:
                div_info = "[Div. 3] "
            elif "Div. 4" in contest.name:
                div_info = "[Div. 4] "

            # Calculate duration string
            duration_str = ""
            if contest.duration_seconds:
                hours = contest.duration_seconds // 3600
                minutes = (contest.duration_seconds % 3600) // 60
                duration_str = f"{hours}h" if minutes == 0 else f"{hours}h {minutes}m"

            timestamp = int(contest.start_time_utc.timestamp())
            time_str = f"<t:{timestamp}:F> (<t:{timestamp}:R>)"

            value = f"**Time:** {time_str}\n"
            if duration_str:
                value += f"**Duration:** {duration_str}\n"
            value += f"**Link:** [Join Contest]({contest.url})"

            embed.add_field(
                name=f"{div_info}{contest.name}",
                value=value,
                inline=False,
            )

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="refresh-codeforces-contests",
        description="Admin-only: Force a sync of Codeforces contests",
    )
    @app_commands.default_permissions(administrator=True)
    async def refresh_codeforces(self, interaction: discord.Interaction) -> None:
        """Force a manual sync of Codeforces contests."""
        await interaction.response.defer(ephemeral=True)

        cf_contests = await cf_provider.fetch_contests()
        if not cf_contests:
            await interaction.followup.send("Failed to fetch contests from Codeforces. Check logs.")
            return

        added, updated = await contest_service.sync_codeforces_contests(cf_contests)
        await interaction.followup.send(
            f"✅ Sync complete! Added **{added}** new contests and updated **{updated}** existing ones."
        )


async def setup(bot: commands.Bot) -> None:
    """Load the Contests cog."""
    await bot.add_cog(Contests(bot))
