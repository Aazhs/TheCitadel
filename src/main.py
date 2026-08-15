"""Entry-point for The Citadel Bot."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiohttp import web

from src.bot import create_bot, load_extensions
from src.config import get_settings
from src.utils.logging import setup_logging

logger = logging.getLogger("arena.main")


async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="The Citadel Bot is running!")

async def start_web_server() -> None:
    """Start a dummy web server so Render doesn't kill the service."""
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Dummy web server listening on port %s for Render health checks", port)

async def _run() -> None:
    settings = get_settings()
    setup_logging(level=settings.log_level)

    logger.info(
        "Starting The Citadel Bot — environment=%s",
        settings.environment,
    )

    # Initialise database if configured
    if settings.database_url:
        from src.db.engine import close_db, init_db

        init_db(settings.database_url)
        logger.info("Database layer initialised")
    else:
        logger.warning("DATABASE_URL not set — database features disabled")

    # Start the dummy web server
    await start_web_server()

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
