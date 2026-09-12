"""Bot factory — creates and configures the discord.py Bot instance."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from src.config import get_settings

logger = logging.getLogger("arena.bot")

COG_EXTENSIONS: list[str] = [
    "src.cogs.health",
    "src.cogs.admin_health",
    "src.cogs.setup",
    "src.cogs.onboarding",
    "src.cogs.profile",
    "src.cogs.contests",
    "src.cogs.reminders",
    "src.cogs.events",
    "src.cogs.lifecycle",
    "src.cogs.submissions",
    "src.cogs.leaderboard",
    "src.cogs.stats",
    "src.cogs.roles",
]


def create_bot() -> commands.Bot:
    """Build a configured Bot instance with required intents."""
    settings = get_settings()

    intents = discord.Intents.default()
    intents.members = True  # required for on_member_join

    # Enable message content intent only when accountability cog needs DM text
    if settings.accountability_enabled:
        intents.message_content = True
        logger.info("Message Content Intent enabled (accountability cog)")
    else:
        intents.message_content = False  # not needed for slash commands

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

    # Conditionally load the accountability cog — never crash the bot on failure
    settings = get_settings()
    if settings.accountability_enabled:
        if settings.accountability_user_id and settings.accountability_guild_id:
            try:
                await bot.load_extension("src.cogs.accountability")
                logger.info(
                    "Loaded accountability cog (user: %s, guild: %s)",
                    settings.accountability_user_id,
                    settings.accountability_guild_id,
                )
            except Exception:
                logger.warning("Accountability cog failed to load — skipping", exc_info=True)
        else:
            missing = []
            if not settings.accountability_user_id:
                missing.append("ACCOUNTABILITY_USER_ID")
            if not settings.accountability_guild_id:
                missing.append("ACCOUNTABILITY_GUILD_ID")
            logger.warning(
                "ACCOUNTABILITY_ENABLED=true but missing %s — skipping",
                ", ".join(missing),
            )
    else:
        logger.info("Accountability cog disabled (ACCOUNTABILITY_ENABLED=false)")


