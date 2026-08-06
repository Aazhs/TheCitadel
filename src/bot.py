"""Bot factory — creates and configures the discord.py Bot instance."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

logger = logging.getLogger("arena.bot")

COG_EXTENSIONS: list[str] = [
    "src.cogs.health",
    "src.cogs.admin_health",
    "src.cogs.setup",
    "src.cogs.onboarding",
    "src.cogs.profile",
    "src.cogs.contests",
    "src.cogs.reminders",
]


def create_bot() -> commands.Bot:
    """Build a configured Bot instance with required intents."""
    intents = discord.Intents.default()
    intents.message_content = False  # not needed for slash commands
    intents.members = True  # required for on_member_join

    bot = commands.Bot(
        command_prefix=commands.when_mentioned,  # slash-command only
        intents=intents,
        help_command=None,
    )

    @bot.event
    async def on_ready() -> None:
        """Fires once when the bot has connected and is ready."""
        assert bot.user is not None
        logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
        logger.info("Connected to %d guild(s)", len(bot.guilds))

        # Sync application commands globally
        synced = await bot.tree.sync()
        logger.info("Synced %d slash command(s)", len(synced))

    return bot


async def load_extensions(bot: commands.Bot) -> None:
    """Load all registered cog extensions."""
    for ext in COG_EXTENSIONS:
        try:
            await bot.load_extension(ext)
            logger.info("Loaded extension: %s", ext)
        except Exception:
            logger.exception("Failed to load extension: %s", ext)
            raise
