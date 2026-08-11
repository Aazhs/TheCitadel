"""Entry-point for Algorithm Arena Bot."""

from __future__ import annotations

import asyncio
import logging
import sys

from src.bot import create_bot, load_extensions
from src.config import get_settings
from src.utils.logging import setup_logging

logger = logging.getLogger("arena.main")


async def _run() -> None:
    settings = get_settings()
    setup_logging(level=settings.log_level)

    logger.info(
        "Starting Algorithm Arena Bot — environment=%s",
        settings.environment,
    )

    # Initialise database if configured
    if settings.database_url:
        from src.db.engine import close_db, init_db

        init_db(settings.database_url)
        logger.info("Database layer initialised")
    else:
        logger.warning("DATABASE_URL not set — database features disabled")

    bot = create_bot()

    @bot.event
    async def setup_hook() -> None:
        """Load extensions after the client is internally initialised.

        This ensures that cog background tasks calling ``wait_until_ready()``
        in their ``before_loop`` hooks don't blow up with
        "Client has not been properly initialised".
        """
        await load_extensions(bot)

    try:
        async with bot:
            await bot.start(settings.discord_token)
    finally:
        if settings.database_url:
            from src.db.engine import close_db

            await close_db()


def main() -> None:
    """Synchronous entry-point."""
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("Bot shut down by user")
    except Exception:
        logger.exception("Fatal error during bot startup")
        sys.exit(1)


if __name__ == "__main__":
    main()
