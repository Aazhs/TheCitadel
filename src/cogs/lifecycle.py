import logging
from datetime import UTC, datetime

import discord
from discord.ext import commands, tasks

from src.cogs.submissions import SubmitResultsView
from src.config import get_settings
from src.services import audit as audit_service
from src.services import guild_settings as gs_service
from src.services import lifecycle as lifecycle_service

logger = logging.getLogger("arena.cogs.lifecycle")


class Lifecycle(commands.Cog):
    """Cog for managing event lifecycles via a background loop."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.lifecycle_check.change_interval(seconds=get_settings().event_check_interval_seconds)

    async def cog_load(self) -> None:
        """Start the background task when the cog is loaded."""
        self.lifecycle_check.start()
        self.cycle_rollover_check.start()

    async def cog_unload(self) -> None:
        """Stop the background task when the cog is unloaded."""
        self.lifecycle_check.cancel()
        self.cycle_rollover_check.cancel()

    @tasks.loop(seconds=60)
    async def lifecycle_check(self) -> None:
        """Background task that manages event lifecycle state transitions."""
        try:
            now = datetime.now(UTC)
            app_settings = get_settings()

            # 1. Activate events
            events_to_activate = await lifecycle_service.get_events_to_activate(now)
            for event in events_to_activate:
                try:
                    await lifecycle_service.activate_event(event.id)
                    channel_id = event.discussion_channel_id or event.announcement_channel_id
                    if not channel_id:
                        logger.warning(
                            "No discussion or announcement channel for event %s", event.id
                        )
                    else:
                        channel = self.bot.get_channel(int(channel_id))
                        if not channel:
                            logger.warning(
                                "Channel %s not found for event %s", channel_id, event.id
                            )
                        else:
                            embed = discord.Embed(
                                title="⚔️ The Citadel — Contest Started",
                                description=f"{event.title}\n{event.description or ''}",
                                color=discord.Color.gold(),
                            )
                            start_ts = int(event.start_time_utc.timestamp())
                            end_ts = int(event.end_time_utc.timestamp())
                            embed.add_field(name="Start Time", value=f"<t:{start_ts}:F>")
                            embed.add_field(name="End Time", value=f"<t:{end_ts}:F>")

                            guild_settings = await gs_service.get_settings(str(event.guild_settings.discord_guild_id))
                            content = f"<@&{guild_settings.alert_role_id}>" if guild_settings and guild_settings.alert_role_id else ""
                            await channel.send(content=content, embed=embed)
                    await audit_service.log_action(
                        event.guild_settings_id,
                        "activate_event",
                        "SYSTEM",
                        target_type="event",
                        target_id=event.id,
                    )
                except Exception:
                    logger.exception("Error activating event %s", event.id)

            # 2. End events
            events_to_end = await lifecycle_service.get_events_to_end(now)
            for event in events_to_end:
                try:
                    await lifecycle_service.end_event(event.id, app_settings.submission_deadline_hours)
                    if not event.results_channel_id:
                        logger.warning("No results channel for event %s", event.id)
                    else:
                        channel = self.bot.get_channel(int(event.results_channel_id))
                        if not channel:
                            logger.warning(
                                "Channel %s not found for event %s",
                                event.results_channel_id,
                                event.id,
                            )
                        else:
                            embed = discord.Embed(
                                title="🏁 Contest Ended — Submit Your Results",
                                description=f"The event has ended. You have {app_settings.submission_deadline_hours} hours to submit your results.",
                                color=discord.Color.blue(),
                            )
                            view = SubmitResultsView(event.id)
                            gs = await gs_service.get_settings(str(event.guild_settings.discord_guild_id))
                            content = f"<@&{gs.alert_role_id}>" if gs and gs.alert_role_id else ""
                            await channel.send(content=content, embed=embed, view=view)
                    await audit_service.log_action(
                        event.guild_settings_id,
                        "end_event",
                        "SYSTEM",
                        target_type="event",
                        target_id=event.id,
                    )
                except Exception:
                    logger.exception("Error ending event %s", event.id)

            # 3. Finalize events
            events_to_finalize = await lifecycle_service.get_events_to_finalize(now)
            for event in events_to_finalize:
                try:
                    await lifecycle_service.finalize_event(event.id)
                    if event.results_channel_id:
                        channel = self.bot.get_channel(int(event.results_channel_id))
                        if channel:
                            embed = discord.Embed(
                                title="🔒 Submissions Closed",
                                color=discord.Color.dark_grey(),
                            )
                            gs = await gs_service.get_settings(str(event.guild_settings.discord_guild_id))
                            content = f"<@&{gs.alert_role_id}>" if gs and gs.alert_role_id else ""
                            await channel.send(content=content, embed=embed)
                    await audit_service.log_action(
                        event.guild_settings_id,
                        "finalize_event",
                        "SYSTEM",
                        target_type="event",
                        target_id=event.id,
                    )
                except Exception:
                    logger.exception("Error finalizing event %s", event.id)

        except Exception:
            logger.exception("Error in lifecycle_check loop")

    @lifecycle_check.before_loop
    async def before_lifecycle_check(self) -> None:
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()


    @tasks.loop(hours=24)
    async def cycle_rollover_check(self) -> None:
        """Daily task to ensure all members' cycle points are correctly zeroed if a new 2-week cycle started."""
        try:
            from src.db.engine import get_session_factory
            from src.db.models import GuildMember
            from sqlalchemy import select
            from src.services.stats import recompute_member_stats
            
            factory = get_session_factory()
            async with factory() as session:
                # To ensure everyone's current_cycle points are accurate relative to the *current* cycle start,
                # we just recompute everyone. Since recompute filters points by current_cycle_start, 
                # anyone who hasn't participated yet this cycle will drop to 0.
                stmt = select(GuildMember.id)
                member_ids = (await session.scalars(stmt)).all()
                
                count = 0
                for mid in member_ids:
                    await recompute_member_stats(session, mid)
                    count += 1
                
                if count > 0:
                    await session.commit()
                    logger.info("Cycle rollover check completed. Recomputed %d members.", count)
                    
        except Exception:
            logger.exception("Error in cycle_rollover_check loop")

    @cycle_rollover_check.before_loop
    async def before_cycle_rollover_check(self) -> None:
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Lifecycle(bot))
