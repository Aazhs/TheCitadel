"""Events cog — admin event management and member registration commands."""

from __future__ import annotations

import logging
import zoneinfo
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from src.services import events as event_service
from src.services import guild_settings as gs_service
from src.services import linked_accounts as la_service

logger = logging.getLogger("arena.cogs.events")

# ── Event type choices for slash commands ─────────────────────────────

EVENT_TYPE_CHOICES = [
    app_commands.Choice(name="Codeforces Contest", value="codeforces_contest"),
    app_commands.Choice(name="CodeChef Contest", value="codechef_contest"),
    app_commands.Choice(name="LeetCode Contest", value="leetcode_contest"),
    app_commands.Choice(name="Custom Practice", value="custom_practice"),
    app_commands.Choice(name="Daily LeetCode", value="daily_leetcode"),
]

# ── Persistent Register button view ──────────────────────────────────


class RegisterButtonView(discord.ui.View):
    """A persistent view with a Register button for event announcements.

    Uses a custom_id that includes the event ID so it survives bot restarts.
    """

    def __init__(self, event_id: int) -> None:
        super().__init__(timeout=None)
        self.event_id = event_id

        # Create button with persistent custom_id
        button = discord.ui.Button(
            label="Register",
            style=discord.ButtonStyle.green,
            custom_id=f"event_register:{event_id}",
            emoji="✋",
        )
        self.add_item(button)


# ── Helper: parse datetime string ────────────────────────────────────


async def _update_event_message(
    interaction: discord.Interaction, event_id: int, guild_id: str
) -> None:
    """Helper to update both the interaction message and the main announcement message."""
    try:
        event = await event_service.get_event(event_id, guild_id)
        if not event:
            return

        reg_count = await event_service.get_registration_count(event.id)
        embed = _build_event_embed(event, registration_count=reg_count)

        # 1. Update the message the user clicked on (if applicable)
        if interaction.message:
            try:
                await interaction.message.edit(embed=embed)
            except Exception:
                pass

        # 2. Update the main announcement message if it exists and is different
        if event.announcement_channel_id and event.announcement_message_id and interaction.guild:
            if interaction.message and str(interaction.message.id) == event.announcement_message_id:
                return  # Already updated above

            channel = interaction.guild.get_channel(int(event.announcement_channel_id))
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    msg = await channel.fetch_message(int(event.announcement_message_id))
                    await msg.edit(embed=embed)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
    except Exception as e:
        logger.warning(f"Failed to update event messages for {event_id}: {e}")


def _parse_datetime(value: str, tz_name: str) -> datetime:
    """Parse a datetime string in the given timezone, return as UTC.

    Supports multiple formats:
    - ``YYYY-MM-DD HH:MM``       (24-hour, e.g. 20:00 for 8 PM)
    - ``YYYY-MM-DD HH:MM AM/PM`` (12-hour, e.g. 8:00 PM)
    - ``YYYY-MM-DD H:MM AM/PM``  (12-hour without leading zero)

    Raises:
        ValueError: If the string doesn't match any supported format.
    """
    formats = [
        "%Y-%m-%d %H:%M",      # 24-hour: 2026-08-28 20:00
        "%Y-%m-%d %I:%M %p",   # 12-hour: 2026-08-28 8:00 PM
        "%Y-%m-%d %I:%M%p",    # 12-hour no space: 2026-08-28 8:00PM
    ]
    value = value.strip()
    tz = zoneinfo.ZoneInfo(tz_name)

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=tz).astimezone(UTC)
        except ValueError:
            continue

    raise ValueError(
        f"Invalid datetime: `{value}`.\n"
        "Use **24-hour format**: `YYYY-MM-DD HH:MM` (e.g. `2026-08-28 20:00` for 8 PM)\n"
        "Or **12-hour format**: `YYYY-MM-DD HH:MM AM/PM` (e.g. `2026-08-28 8:00 PM`)"
    )


# ── Helper: build event embed ────────────────────────────────────────


def _build_event_embed(event: object, *, registration_count: int | None = None) -> discord.Embed:
    """Build a rich embed for an event."""
    # Map event types to display names
    type_display = {
        "codeforces_contest": "🏆 Codeforces Contest",
        "codechef_contest": "🍳 CodeChef Contest",
        "leetcode_contest": "💻 LeetCode Contest",
        "custom_practice": "📝 Custom Practice",
        "daily_leetcode": "📅 Daily LeetCode",
    }

    # Map status to emoji
    status_display = {
        "draft": "📝 Draft",
        "published": "📢 Published",
        "registration_open": "📋 Registration Open",
        "submission_open": "📝 Submissions Open",
        "active": "🟢 Active",
        "ended": "🏁 Ended",
        "finalized": "🏁 Finalized",
        "cancelled": "❌ Cancelled",
    }

    color_map = {
        "draft": discord.Color.light_grey(),
        "published": discord.Color.blue(),
        "registration_open": discord.Color.green(),
        "submission_open": discord.Color.orange(),
        "active": discord.Color.gold(),
        "ended": discord.Color.dark_grey(),
        "finalized": discord.Color.dark_grey(),
        "cancelled": discord.Color.red(),
    }

    embed = discord.Embed(
        title=event.title,
        description=event.description,
        color=color_map.get(event.status, discord.Color.blurple()),
        url=event.official_url if event.official_url else None,
    )

    embed.add_field(
        name="Type",
        value=type_display.get(event.event_type, event.event_type),
        inline=True,
    )
    embed.add_field(
        name="Status",
        value=status_display.get(event.status, event.status),
        inline=True,
    )

    if event.platform:
        embed.add_field(name="Platform", value=event.platform.title(), inline=True)

    start_ts = int(event.start_time_utc.timestamp())
    end_ts = int(event.end_time_utc.timestamp())
    embed.add_field(
        name="Start",
        value=f"<t:{start_ts}:F> (<t:{start_ts}:R>)",
        inline=True,
    )
    embed.add_field(
        name="End",
        value=f"<t:{end_ts}:F>",
        inline=True,
    )

    if event.registration_deadline_utc:
        dl_ts = int(event.registration_deadline_utc.timestamp())
        embed.add_field(
            name="Registration Deadline",
            value=f"<t:{dl_ts}:F> (<t:{dl_ts}:R>)",
            inline=True,
        )

    if registration_count is not None:
        embed.add_field(
            name="Registered",
            value=str(registration_count),
            inline=True,
        )

    embed.set_footer(text=f"Event ID: {event.id}")
    return embed


# ── Events cog ────────────────────────────────────────────────────────


class Events(commands.Cog):
    """Cog for admin event management and member registration."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Register persistent views for any existing published events."""
        # We register a dynamic view handler instead of individual views
        self.bot.add_dynamic_items(DynamicRegisterButton)

    async def cog_unload(self) -> None:
        """Clean up dynamic items."""
        self.bot.remove_dynamic_items(DynamicRegisterButton)

    # ── Admin commands ────────────────────────────────────────────────

    @app_commands.command(
        name="event-create",
        description="Create a new coding event (admin only)",
    )
    @app_commands.describe(
        title="Event title",
        event_type="Type of event",
        start_time="Start time in YYYY-MM-DD HH:MM format (Local Time)",
        end_time="End time in YYYY-MM-DD HH:MM format (Local Time)",
        description="Event description",
        announcement_channel="Channel for the event announcement",
        platform="Platform name (optional)",
        official_url="Official URL for the event (optional)",
        discussion_channel="Channel for event discussion (optional)",
        results_channel="Channel for results (optional)",
    )
    @app_commands.choices(event_type=EVENT_TYPE_CHOICES)
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def event_create(
        self,
        interaction: discord.Interaction,
        title: str,
        event_type: app_commands.Choice[str],
        start_time: str,
        end_time: str,
        description: str,
        announcement_channel: discord.TextChannel,
        platform: str | None = None,
        official_url: str | None = None,
        discussion_channel: discord.TextChannel | None = None,
        results_channel: discord.TextChannel | None = None,
    ) -> None:
        """Create a new event in draft status."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        try:
            settings = await gs_service.get_or_create(str(interaction.guild.id))
            start_dt = _parse_datetime(start_time, settings.timezone)
            end_dt = _parse_datetime(end_time, settings.timezone)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return

        try:
            event = await event_service.create_event(
                guild_id=str(interaction.guild.id),
                title=title,
                event_type=event_type.value,
                description=description,
                start_time_utc=start_dt,
                end_time_utc=end_dt,
                created_by_discord_user_id=str(interaction.user.id),
                platform=platform,
                official_url=official_url,
                announcement_channel_id=str(announcement_channel.id),
                discussion_channel_id=str(discussion_channel.id) if discussion_channel else None,
                results_channel_id=str(results_channel.id) if results_channel else None,
            )
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return

        embed = _build_event_embed(event)
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())
        await interaction.followup.send(
            f"✅ Event **{event.title}** created (ID: `{event.id}`).\n"
            f"📅 Start: <t:{start_ts}:F> — End: <t:{end_ts}:F>\n"
            f"*(Verify the times above are correct before publishing!)*\n\n"
            f"Use `/event-publish event_id:{event.id}` to announce it.",
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="event-edit",
        description="Edit an existing event's details (admin only)",
    )
    @app_commands.describe(
        event_id="The ID of the event to edit",
        title="New event title (optional)",
        description="New event description (optional)",
        official_url="New official URL (optional)",
        start_time="New start time in YYYY-MM-DD HH:MM format (Local Time) (optional)",
        end_time="New end time in YYYY-MM-DD HH:MM format (Local Time) (optional)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def event_edit(
        self,
        interaction: discord.Interaction,
        event_id: int,
        title: str | None = None,
        description: str | None = None,
        official_url: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> None:
        """Update an existing event."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)

        try:
            settings = await gs_service.get_or_create(guild_id)
            start_dt = _parse_datetime(start_time, settings.timezone) if start_time else None
            end_dt = _parse_datetime(end_time, settings.timezone) if end_time else None

            event = await event_service.update_event(
                event_id=event_id,
                guild_id=guild_id,
                title=title,
                description=description,
                official_url=official_url,
                start_time_utc=start_dt,
                end_time_utc=end_dt,
            )
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return

        # Update announcement if published
        if event.announcement_channel_id and event.announcement_message_id:
            channel = interaction.guild.get_channel(int(event.announcement_channel_id))
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    msg = await channel.fetch_message(int(event.announcement_message_id))
                    reg_count = await event_service.get_registration_count(event.id)
                    embed = _build_event_embed(event, registration_count=reg_count)
                    await msg.edit(embed=embed)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    logger.warning("Could not update announcement for edited event %s", event_id)

        await interaction.followup.send(
            f"✅ Event **{event.title}** (ID: `{event.id}`) has been updated.",
            embed=_build_event_embed(event),
            ephemeral=True,
        )

    @app_commands.command(
        name="event-publish",
        description="Publish a draft event and announce it (admin only)",
    )
    @app_commands.describe(event_id="The ID of the event to publish")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def event_publish(
        self,
        interaction: discord.Interaction,
        event_id: int,
    ) -> None:
        """Publish an event: post announcement embed with Register button."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)

        try:
            event = await event_service.publish_event(event_id, guild_id)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return

        # Post announcement to configured channel
        if event.announcement_channel_id:
            channel = interaction.guild.get_channel(int(event.announcement_channel_id))
            if channel and isinstance(channel, discord.TextChannel):
                embed = _build_event_embed(event, registration_count=0)
                view = RegisterButtonView(event.id)
                
                settings = await gs_service.get_settings(guild_id)
                content = f"<@&{settings.alert_role_id}>" if settings and settings.alert_role_id else ""
                
                try:
                    msg = await channel.send(content=content, embed=embed, view=view)
                    await event_service.update_announcement_message_id(event.id, str(msg.id))
                except discord.Forbidden:
                    await interaction.followup.send(
                        f"⚠️ Event published but I couldn't post to "
                        f"<#{event.announcement_channel_id}> (missing permissions).",
                        ephemeral=True,
                    )
                    return

        # Post discussion starter if configured
        if event.discussion_channel_id:
            disc_channel = interaction.guild.get_channel(int(event.discussion_channel_id))
            if disc_channel and isinstance(disc_channel, discord.TextChannel):
                try:
                    await disc_channel.send(
                        f"💬 **Discussion: {event.title}**\n\n"
                        f"Use this channel to discuss the event. "
                        f"Good luck to all participants! 🍀"
                    )
                except discord.Forbidden:
                    logger.warning(
                        "Could not post discussion starter to channel %s",
                        event.discussion_channel_id,
                    )

        await interaction.followup.send(
            f"✅ Event **{event.title}** has been published and announced!",
            ephemeral=True,
        )

    @app_commands.command(
        name="event-cancel",
        description="Cancel an event (admin only)",
    )
    @app_commands.describe(event_id="The ID of the event to cancel")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def event_cancel(
        self,
        interaction: discord.Interaction,
        event_id: int,
    ) -> None:
        """Cancel an event and update the announcement if possible."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)

        try:
            event = await event_service.cancel_event(event_id, guild_id)
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return

        # Try to update the announcement embed
        if event.announcement_channel_id and event.announcement_message_id:
            channel = interaction.guild.get_channel(int(event.announcement_channel_id))
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    msg = await channel.fetch_message(int(event.announcement_message_id))
                    cancelled_embed = _build_event_embed(event)
                    # Remove the Register button from cancelled events
                    await msg.edit(embed=cancelled_embed, view=None)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    logger.warning("Could not update announcement for cancelled event %s", event_id)

        await interaction.followup.send(
            f"✅ Event **{event.title}** has been cancelled.",
            ephemeral=True,
        )

    @app_commands.command(
        name="event-list",
        description="List all active events for this server",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def event_list(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """List non-cancelled/ended events."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        events = await event_service.list_events(str(interaction.guild.id))

        if not events:
            await interaction.followup.send(
                "📭 No active events found for this server.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📅 Server Events",
            color=discord.Color.blurple(),
        )

        status_emoji = {
            "draft": "📝",
            "published": "📢",
            "registration_open": "📋",
            "active": "🟢",
        }

        for event in events:
            emoji = status_emoji.get(event.status, "❓")
            start_info = "Not scheduled"
            if event.start_time_utc:
                start_ts = int(event.start_time_utc.timestamp())
                start_info = f"<t:{start_ts}:R>"
            embed.add_field(
                name=f"{emoji} {event.title} (ID: {event.id})",
                value=(
                    f"**Type:** {event.event_type.replace('_', ' ').title()}\n"
                    f"**Status:** {event.status.title()}\n"
                    f"**Starts:** {start_info}"
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="event-view",
        description="View detailed info about an event",
    )
    @app_commands.describe(event_id="The ID of the event to view")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def event_view(
        self,
        interaction: discord.Interaction,
        event_id: int,
    ) -> None:
        """Show detailed event info with registration count."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)
        event = await event_service.get_event(event_id, guild_id)

        if event is None:
            await interaction.followup.send(
                f"❌ Event with ID `{event_id}` not found.", ephemeral=True
            )
            return

        reg_count = await event_service.get_registration_count(event_id)
        embed = _build_event_embed(event, registration_count=reg_count)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Member commands ───────────────────────────────────────────────

    @app_commands.command(
        name="register",
        description="Register for a coding event",
    )
    @app_commands.describe(event_id="The ID of the event to register for")
    @app_commands.guild_only()
    async def register(
        self,
        interaction: discord.Interaction,
        event_id: int,
    ) -> None:
        """Register the invoking user for an event."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        # Check Codeforces account requirement
        if event_service.REQUIRE_CF_LINK_FOR_CF_EVENTS:
            event = await event_service.get_event(event_id, guild_id)
            if event and event.event_type == "codeforces_contest":
                accounts = await la_service.get_member_accounts(guild_id, user_id)
                has_cf = any(a.platform == "codeforces" for a in accounts)
                if not has_cf:
                    await interaction.followup.send(
                        "❌ You must link your Codeforces account first with "
                        "`/link-codeforces` before registering for Codeforces events.",
                        ephemeral=True,
                    )
                    return

        try:
            await event_service.register_for_event(event_id, guild_id, user_id)
            await interaction.followup.send(
                "✅ You have been registered for this event! Good luck! 🎯",
                ephemeral=True,
            )
        except ValueError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)

    @app_commands.command(
        name="my-events",
        description="Show events you are registered for",
    )
    @app_commands.guild_only()
    async def my_events(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Show events the user is registered for."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        events = await event_service.get_user_events(
            str(interaction.guild.id), str(interaction.user.id)
        )

        if not events:
            await interaction.followup.send(
                "📭 You are not registered for any events.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📋 Your Events",
            color=discord.Color.green(),
        )

        for event in events:
            start_ts = int(event.start_time_utc.timestamp())
            embed.add_field(
                name=f"{event.title} (ID: {event.id})",
                value=(
                    f"**Status:** {event.status.title()}\n"
                    f"**Starts:** <t:{start_ts}:F> (<t:{start_ts}:R>)"
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)


# ── Dynamic button for persistence across restarts ────────────────────


class DynamicRegisterButton(
    discord.ui.DynamicItem[discord.ui.Button], template=r"event_register:(?P<event_id>\d+)"
):
    """Dynamic item that handles Register button clicks across bot restarts."""

    def __init__(self, event_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Register",
                style=discord.ButtonStyle.green,
                custom_id=f"event_register:{event_id}",
                emoji="✋",
            )
        )
        self.event_id = event_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: __import__("re").Match[str],
    ) -> DynamicRegisterButton:
        """Reconstruct the item from the custom_id regex match."""
        event_id = int(match.group("event_id"))
        return cls(event_id)

    async def callback(self, interaction: discord.Interaction) -> None:
        """Handle the Register button click."""
        assert interaction.guild is not None

        await interaction.response.defer(ephemeral=True)

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        # Check Codeforces account requirement
        if event_service.REQUIRE_CF_LINK_FOR_CF_EVENTS:
            try:
                event = await event_service.get_event(self.event_id, guild_id)
                if event and event.event_type == "codeforces_contest":
                    accounts = await la_service.get_member_accounts(guild_id, user_id)
                    has_cf = any(a.platform == "codeforces" for a in accounts)
                    if not has_cf:
                        await interaction.followup.send(
                            "❌ You must link your Codeforces account first with "
                            "`/link-codeforces` before registering for Codeforces events.",
                            ephemeral=True,
                        )
                        return
            except Exception:
                logger.exception("Error checking CF link for event %s", self.event_id)

        try:
            await event_service.register_for_event(self.event_id, guild_id, user_id)
            await _update_event_message(interaction, self.event_id, guild_id)
            await interaction.followup.send(
                "✅ You have been registered for this event! Good luck! 🎯",
                ephemeral=True,
            )
        except ValueError as e:
            await interaction.followup.send(
                f"❌ {e}",
                ephemeral=True,
            )
        except Exception:
            logger.exception("Unexpected error during button registration")
            await interaction.followup.send(
                "❌ An unexpected error occurred. Please try again later.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    """Load the Events cog."""
    await bot.add_cog(Events(bot))
    logger.info("Events cog loaded")
