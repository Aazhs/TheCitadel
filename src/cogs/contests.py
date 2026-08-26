"""Contests cog for The Citadel."""

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.providers import codeforces as cf_provider
from src.services import contests as contest_service
from src.cogs.events import _build_event_embed, RegisterButtonView
from src.services import events as event_service
from src.services import guild_settings as gs_service


logger = logging.getLogger("arena.cogs.contests")



class CreateEventSelect(discord.ui.Select):
    def __init__(self, contests: list):
        self.contests = contests
        
        options = []
        for i, c in enumerate(contests[:25]):
            options.append(discord.SelectOption(
                label=c.name[:100],
                value=str(i),
                description=f"{c.platform.title()} - {c.start_time_utc.strftime('%b %d %H:%M UTC')}"
            ))
            
        super().__init__(
            placeholder="Select a contest to create an event...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return
            
        idx = int(self.values[0])
        contest = self.contests[idx]
        
        try:
            # 1. Find channels
            announcements_ch = discord.utils.get(guild.text_channels, name="announcements")
            discussions_ch = discord.utils.get(guild.text_channels, name="discussions")
            results_ch = discord.utils.get(guild.text_channels, name="results")
            
            if not announcements_ch:
                await interaction.followup.send("❌ Could not find `#announcements` channel to publish the event.", ephemeral=True)
                return
                
            # Compute end time using duration if available
            import datetime
            if contest.duration_seconds:
                end_time = contest.start_time_utc + datetime.timedelta(seconds=contest.duration_seconds)
            else:
                end_time = contest.start_time_utc + datetime.timedelta(hours=2)

            # 2. Create Event
            event = await event_service.create_event(
                guild_id=str(guild.id),
                title=contest.name,
                event_type=f"{contest.platform}_contest",
                description=f"Automated event for {contest.name}",
                start_time_utc=contest.start_time_utc,
                end_time_utc=end_time,
                created_by_discord_user_id=str(interaction.user.id),
                platform=contest.platform,
                official_url=contest.url,
                announcement_channel_id=str(announcements_ch.id),
                discussion_channel_id=str(discussions_ch.id) if discussions_ch else None,
                results_channel_id=str(results_ch.id) if results_ch else None,
            )
            
            # 3. Publish Event
            event = await event_service.publish_event(event.id, str(guild.id))
            
            # 4. Announce it
            embed = _build_event_embed(event, registration_count=0)
            view = RegisterButtonView(event.id)
            
            settings = await gs_service.get_settings(str(guild.id))
            content = f"<@&{settings.alert_role_id}>" if settings and settings.alert_role_id else ""
            
            try:
                msg = await announcements_ch.send(content=content, embed=embed, view=view)
                await event_service.update_announcement_message_id(event.id, str(msg.id))
            except discord.Forbidden:
                await interaction.followup.send("⚠️ Created event but missing permissions to post in `#announcements`.", ephemeral=True)
                return
                
            if discussions_ch:
                try:
                    await discussions_ch.send(
                        f"💬 **Discussion: {event.title}**\n\n"
                        f"Use this channel to discuss the event. Good luck to all participants! 🍀"
                    )
                except discord.Forbidden:
                    pass
            
            await interaction.followup.send(f"✅ Event **{event.title}** created and published in {announcements_ch.mention}!", ephemeral=True)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ Failed to create event: {e}", ephemeral=True)

class CreateEventView(discord.ui.View):
    def __init__(self, contests: list):
        super().__init__(timeout=None)
        self.add_item(CreateEventSelect(contests))


class Contests(commands.Cog):
    """Cog for contest discovery and syncing."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._sync_task_started = False

    async def cog_load(self) -> None:
        """Start background tasks when cog is loaded."""
        import asyncio
        if not self._sync_task_started:
            self.sync_contests_loop.start()
            self.auto_event_creator.start()
            self._sync_task_started = True
        # Run an immediate sync on startup so the DB is fresh right away
        asyncio.ensure_future(self._do_initial_sync())

    async def cog_unload(self) -> None:
        """Cancel background tasks when cog is unloaded."""
        self.sync_contests_loop.cancel()
        self.auto_event_creator.cancel()
        self._sync_task_started = False

    async def _do_initial_sync(self) -> None:
        """Run a single contest sync immediately on startup so the DB isn't stale."""
        import asyncio
        from src.providers import codechef as cc_provider
        from src.providers import leetcode as lc_provider

        await self.bot.wait_until_ready()
        # Small delay to let everything settle
        await asyncio.sleep(5)

        logger.info("Running initial contest sync on startup...")
        providers = [
            ("Codeforces", cf_provider.fetch_contests, contest_service.sync_codeforces_contests),
            ("CodeChef", cc_provider.fetch_contests, contest_service.sync_codechef_contests),
            ("LeetCode", lc_provider.fetch_contests, contest_service.sync_leetcode_contests),
        ]

        for name, fetcher, syncer in providers:
            try:
                contests = await fetcher()
                if contests:
                    added, updated = await syncer(contests)
                    logger.info("Initial %s sync: %d added, %d updated", name, added, updated)
                else:
                    logger.warning("Initial %s sync fetched no contests.", name)
            except Exception as e:
                logger.exception("Error during initial %s sync: %s", name, e)
            await asyncio.sleep(1)


    @app_commands.command(
        name="force-auto-events",
        description="Admin-only: Forcefully run the auto-event creator now for this server",
    )
    @app_commands.default_permissions(administrator=True)
    async def force_auto_events(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self._run_auto_event_creator(force=True, specific_guild_id=str(interaction.guild_id))
        await interaction.followup.send("✅ Forcefully ran auto-event creator for this server!")

    @tasks.loop(minutes=30)
    async def auto_event_creator(self) -> None:
        await self._run_auto_event_creator(force=False)
        
    async def _run_auto_event_creator(self, force: bool = False, specific_guild_id: str = None) -> None:
        import datetime
        from zoneinfo import ZoneInfo
        from sqlalchemy import select
        from src.db.engine import get_session_factory
        from src.db.models import GuildSettings
        from src.services import contests as contest_service
        from src.services import events as event_service
        from src.cogs.events import _build_event_embed, RegisterButtonView

        logger.info(f"Running auto_event_creator check (force={force})...")
        factory = get_session_factory()

        # Fetch guild settings in a dedicated session that is closed before the loop.
        async with factory() as session:
            if specific_guild_id:
                stmt = select(GuildSettings).where(GuildSettings.discord_guild_id == specific_guild_id)
            else:
                stmt = select(GuildSettings).where(GuildSettings.auto_create_events == True)
            result = await session.execute(stmt)
            guilds = result.scalars().all()

        for gs in guilds:
            if not force:
                try:
                    tz = ZoneInfo(gs.timezone)
                except Exception:
                    tz = ZoneInfo("UTC")

                now_local = datetime.datetime.now(tz)

                # Check if it's Saturday (weekday == 5) and hour == 22
                if now_local.weekday() != 5 or now_local.hour != 22:
                    continue

                # Prevent duplicate runs in the same week
                if gs.last_auto_event_run:
                    delta = datetime.datetime.now(datetime.timezone.utc) - gs.last_auto_event_run
                    if delta.total_seconds() < 86400 * 2:
                        continue

            guild = self.bot.get_guild(int(gs.discord_guild_id))
            if not guild:
                continue

            logger.info(f"Auto-creating events for guild {guild.name}")

            # Fetch upcoming contests from all platforms
            upcoming = await contest_service.get_upcoming_contests(limit=20)
            target_contests = [c for c in upcoming if c.platform in ('codechef', 'leetcode', 'codeforces')][:10]

            if not target_contests:
                continue

            announcements_ch = None
            if gs.announcement_channel_id:
                announcements_ch = guild.get_channel(int(gs.announcement_channel_id))

            if not announcements_ch:
                announcements_ch = discord.utils.get(guild.text_channels, name="announcements")

            if not announcements_ch:
                try:
                    await guild.owner.send(
                        f"⚠️ **The Citadel Auto-Event Maker Error**\n"
                        f"I tried to create your weekly events, but I couldn't find an `#announcements` channel! "
                        f"Please create one or set it via `/setup announcement-channel`."
                    )
                except Exception:
                    pass
                continue

            discussions_ch = discord.utils.get(guild.text_channels, name="discussions")
            results_ch = discord.utils.get(guild.text_channels, name="results")

            for contest in target_contests:
                try:
                    if contest.duration_seconds:
                        end_time = contest.start_time_utc + datetime.timedelta(seconds=contest.duration_seconds)
                    else:
                        end_time = contest.start_time_utc + datetime.timedelta(hours=2)

                    # Check for duplicates — use a fresh session each time
                    from src.db.models import Event
                    async with factory() as dup_session:
                        stmt = select(Event).where(
                            Event.guild_settings_id == gs.id,
                            Event.title == contest.name,
                            Event.start_time_utc == contest.start_time_utc
                        )
                        existing = await dup_session.execute(stmt)
                        if existing.scalars().first():
                            logger.info(f"Skipping duplicate event for {contest.name}")
                            continue

                    event = await event_service.create_event(
                        guild_id=str(guild.id),
                        title=contest.name,
                        event_type=f"{contest.platform}_contest",
                        description=f"Automated event for {contest.name}",
                        start_time_utc=contest.start_time_utc,
                        end_time_utc=end_time,
                        created_by_discord_user_id=str(guild.me.id),
                        platform=contest.platform,
                        official_url=contest.url,
                        announcement_channel_id=str(announcements_ch.id),
                        discussion_channel_id=str(discussions_ch.id) if discussions_ch else None,
                        results_channel_id=str(results_ch.id) if results_ch else None,
                    )

                    event = await event_service.publish_event(event.id, str(guild.id))

                    embed = _build_event_embed(event, registration_count=0)
                    view = RegisterButtonView(event.id)

                    content = f"<@&{gs.alert_role_id}>" if gs.alert_role_id else ""
                    msg = await announcements_ch.send(content=content, embed=embed, view=view)
                    await event_service.update_announcement_message_id(event.id, str(msg.id))
                    logger.info(f"Auto-created event '{contest.name}' for guild {guild.name}")

                except Exception as e:
                    logger.error(f"Failed to auto-create event for {contest.name}: {e}")

            if not force:
                from src.services import guild_settings as gs_service
                await gs_service.update_last_auto_event_run(str(guild.id), datetime.datetime.now(datetime.timezone.utc))

    @auto_event_creator.before_loop
    async def before_auto_event_creator(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=6)
    async def sync_contests_loop(self) -> None:
        """Background task to sync Codeforces, CodeChef, and LeetCode contests every 6 hours."""
        import asyncio
        from src.providers import codechef as cc_provider
        from src.providers import leetcode as lc_provider
        
        logger.info("Starting scheduled contest sync for all platforms...")
        
        providers = [
            ("Codeforces", cf_provider.fetch_contests, contest_service.sync_codeforces_contests),
            ("CodeChef", cc_provider.fetch_contests, contest_service.sync_codechef_contests),
            ("LeetCode", lc_provider.fetch_contests, contest_service.sync_leetcode_contests),
        ]
        
        for name, fetcher, syncer in providers:
            try:
                contests = await fetcher()
                if contests:
                    added, updated = await syncer(contests)
                    logger.info("%s sync complete: %d added, %d updated", name, added, updated)
                else:
                    logger.warning("%s sync fetched no contests or failed.", name)
            except Exception as e:
                logger.exception("Error during scheduled %s contest sync: %s", name, e)
                
            await asyncio.sleep(2)

    @sync_contests_loop.before_loop
    async def before_sync_contests(self) -> None:
        """Wait for the bot to be ready before starting the loop."""
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="upcoming",
        description="View upcoming contests across all platforms",
    )
    async def upcoming(self, interaction: discord.Interaction) -> None:
        """Show the next 15 upcoming contests categorized by platform."""
        await interaction.response.defer(ephemeral=False)

        upcoming = await contest_service.get_upcoming_contests(limit=15)

        if not upcoming:
            await interaction.followup.send(
                "No upcoming contests found. They might not be scheduled yet or the bot hasn't synced."
            )
            return

        embed = discord.Embed(
            title="Upcoming Contests",
            color=discord.Color.blue(),
        )

        # Categorize by platform
        platforms = {
            "codeforces": {"name": "Codeforces", "emoji": "🟦", "contests": []},
            "codechef": {"name": "CodeChef", "emoji": "⭐", "contests": []},
            "leetcode": {"name": "LeetCode", "emoji": "🟡", "contests": []},
        }

        for contest in upcoming:
            if contest.platform in platforms:
                platforms[contest.platform]["contests"].append(contest)

        for p_key, p_data in platforms.items():
            if not p_data["contests"]:
                continue
            
            value = ""
            for contest in p_data["contests"]:
                div_info = ""
                if contest.platform == "codeforces":
                    if "Div. 1" in contest.name:
                        div_info = "[Div. 1] "
                    elif "Div. 2" in contest.name:
                        div_info = "[Div. 2] "
                    elif "Div. 3" in contest.name:
                        div_info = "[Div. 3] "
                    elif "Div. 4" in contest.name:
                        div_info = "[Div. 4] "
                        
                duration_str = ""
                if contest.duration_seconds:
                    hours = contest.duration_seconds // 3600
                    minutes = (contest.duration_seconds % 3600) // 60
                    duration_str = f"{hours}h" if minutes == 0 else f"{hours}h {minutes}m"

                timestamp = int(contest.start_time_utc.timestamp())
                
                value += f"**{div_info}{contest.name}**\n"
                value += f"🕒 <t:{timestamp}:F> (<t:{timestamp}:R>)\n"
                if duration_str:
                    value += f"⏳ {duration_str}\n"
                value += f"🔗 [Join Contest]({contest.url})\n\n"
                
            # Truncate if exceeds discord embed field limit
            if len(value) > 1024:
                value = value[:1021] + "..."
                
            embed.add_field(
                name=f"{p_data['emoji']} {p_data['name']}",
                value=value.strip(),
                inline=False,
            )

        view = None
        if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
            if upcoming:
                view = CreateEventView(upcoming)
                
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(
        name="refresh-contests",
        description="Admin-only: Force a sync of all contests",
    )
    @app_commands.default_permissions(administrator=True)
    async def refresh_contests(self, interaction: discord.Interaction) -> None:
        """Force a manual sync of all contests."""
        from src.providers import codechef as cc_provider
        from src.providers import leetcode as lc_provider
        import asyncio
        
        await interaction.response.defer(ephemeral=True)

        providers = [
            ("Codeforces", cf_provider.fetch_contests, contest_service.sync_codeforces_contests),
            ("CodeChef", cc_provider.fetch_contests, contest_service.sync_codechef_contests),
            ("LeetCode", lc_provider.fetch_contests, contest_service.sync_leetcode_contests),
        ]
        
        results = []
        for name, fetcher, syncer in providers:
            try:
                contests = await fetcher()
                if contests:
                    added, updated = await syncer(contests)
                    results.append(f"**{name}**: {added} added, {updated} updated")
                else:
                    results.append(f"**{name}**: Failed to fetch")
            except Exception:
                results.append(f"**{name}**: Error during sync")
                
            await asyncio.sleep(1)

        await interaction.followup.send(
            "✅ **Sync complete!**\n\n" + "\n".join(results)
        )

async def setup(bot: commands.Bot) -> None:
    """Load the Contests cog."""
    await bot.add_cog(Contests(bot))
