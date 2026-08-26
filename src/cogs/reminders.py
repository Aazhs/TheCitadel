"""Reminders cog for scheduling and delivering contest alerts."""

import logging
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.services import guild_settings as guild_service
from src.services import reminders as reminder_service

logger = logging.getLogger("arena.cogs.reminders")

# Human-friendly labels for notification types
_NOTIF_LABELS = {
    "24h": "24 hours",
    "1h": "1 hour",
    "10m": "10 minutes",
}

# Platform colors for reminder embeds
_PLATFORM_COLORS = {
    "codeforces": discord.Color.blue(),
    "codechef": discord.Color.orange(),
    "leetcode": discord.Color.yellow(),
}

# Platform emojis
_PLATFORM_EMOJIS = {
    "codeforces": "🟦",
    "codechef": "⭐",
    "leetcode": "🟡",
}


class Reminders(commands.Cog):
    """Cog for managing and delivering automated contest reminders."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Start the background task when the cog is loaded."""
        self.deliver_reminders_loop.start()

    async def cog_unload(self) -> None:
        """Stop the background task when the cog is unloaded."""
        self.deliver_reminders_loop.cancel()

    @tasks.loop(minutes=2)
    async def deliver_reminders_loop(self) -> None:
        """Background task that schedules and sends reminders."""
        try:
            # First, ensure all upcoming contests have reminders scheduled
            await reminder_service.schedule_missing_deliveries()

            # Second, fetch any deliveries that are due right now.
            # get_due_deliveries() returns plain DeliveryInfo dataclasses, safe after session close.
            due_deliveries = await reminder_service.get_due_deliveries()
            if not due_deliveries:
                return

            now = datetime.now(UTC)

            for delivery in due_deliveries:
                if not delivery.channel_id:
                    await reminder_service.mark_delivery_status(
                        delivery.id, "FAILED", error="No alert channel configured"
                    )
                    continue

                guild = self.bot.get_guild(int(delivery.guild_id))
                if not guild:
                    await reminder_service.mark_delivery_status(
                        delivery.id, "FAILED", error="Guild not found"
                    )
                    continue

                channel = guild.get_channel(int(delivery.channel_id))
                if not channel or not isinstance(channel, discord.TextChannel):
                    await reminder_service.mark_delivery_status(
                        delivery.id, "FAILED", error="Alert channel not found or not a text channel"
                    )
                    continue

                # Build the embed
                start_ts = int(delivery.contest_start_utc.timestamp())
                label = _NOTIF_LABELS.get(delivery.notification_type, delivery.notification_type)
                platform_emoji = _PLATFORM_EMOJIS.get(delivery.contest_platform, "🏆")
                embed_color = _PLATFORM_COLORS.get(delivery.contest_platform, discord.Color.brand_red())

                embed = discord.Embed(
                    title=f"{platform_emoji} {delivery.contest_name}",
                    url=delivery.contest_url or None,
                    color=embed_color,
                    description=f"⏰ Starting in **{label}**!",
                )
                embed.add_field(
                    name="Platform",
                    value=delivery.contest_platform.title(),
                    inline=True,
                )
                embed.add_field(
                    name="Start Time",
                    value=f"<t:{start_ts}:F> (<t:{start_ts}:R>)",
                    inline=True,
                )
                if delivery.contest_duration_seconds:
                    total_mins = delivery.contest_duration_seconds // 60
                    hours, mins = divmod(total_mins, 60)
                    dur_str = f"{hours}h {mins}m" if mins else f"{hours}h"
                    embed.add_field(name="Duration", value=dur_str, inline=True)

                if delivery.contest_url:
                    embed.add_field(
                        name="Link",
                        value=f"[Join Contest]({delivery.contest_url})",
                        inline=False,
                    )

                embed.set_footer(text="The Citadel Contest Alerts")

                # Format ping
                content = ""
                if delivery.alert_role_id:
                    content = f"<@&{delivery.alert_role_id}>"

                try:
                    msg = await channel.send(content=content, embed=embed)
                    await reminder_service.mark_delivery_status(
                        delivery.id, "SENT", sent_at=now, message_id=str(msg.id)
                    )
                    logger.info(
                        "Sent %s reminder for '%s' to guild %s",
                        delivery.notification_type,
                        delivery.contest_name,
                        delivery.guild_id,
                    )
                except discord.Forbidden:
                    await reminder_service.mark_delivery_status(
                        delivery.id, "FAILED", error="Missing Send Messages permission"
                    )
                except Exception as e:
                    logger.error("Failed to send reminder %s: %s", delivery.id, e)
                    await reminder_service.mark_delivery_status(
                        delivery.id, "FAILED", error=str(e)[:500]
                    )

        except Exception as e:
            logger.error("Error in deliver_reminders_loop: %s", e)

    @deliver_reminders_loop.before_loop
    async def before_deliver_reminders_loop(self) -> None:
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

    group = app_commands.Group(name="reminders", description="Manage contest reminders")

    @group.command(name="status", description="Check the status of contest reminders")
    async def status(self, interaction: discord.Interaction) -> None:
        """Check reminder status."""
        await interaction.response.defer(ephemeral=True)

        settings = await guild_service.get_settings(str(interaction.guild_id))

        embed = discord.Embed(
            title="Contest Reminders Status",
            color=discord.Color.green()
            if settings and settings.reminders_enabled
            else discord.Color.red(),
        )

        if not settings:
            embed.description = "This server has not been configured yet. Use `/setup` commands."
            await interaction.followup.send(embed=embed)
            return

        embed.add_field(
            name="Enabled", value="✅ Yes" if settings.reminders_enabled else "❌ No", inline=False
        )

        if settings.contest_alert_channel_id:
            embed.add_field(
                name="Alert Channel", value=f"<#{settings.contest_alert_channel_id}>", inline=True
            )
        else:
            embed.add_field(name="Alert Channel", value="*Not set*", inline=True)

        if settings.alert_role_id:
            embed.add_field(name="Alert Role", value=f"<@&{settings.alert_role_id}>", inline=True)
        else:
            embed.add_field(name="Alert Role", value="*Not set*", inline=True)

        await interaction.followup.send(embed=embed)

    @group.command(name="list", description="List upcoming scheduled contest reminders")
    async def list_reminders(self, interaction: discord.Interaction) -> None:
        """List upcoming reminders for this server (sorted by time)."""
        await interaction.response.defer(ephemeral=True)

        deliveries = await reminder_service.get_pending_deliveries_for_guild(
            str(interaction.guild_id)
        )

        if not deliveries:
            await interaction.followup.send(
                "There are currently no upcoming reminders scheduled for this server."
            )
            return

        # Group deliveries by contest, preserving time order
        contests_dict: dict = {}
        for d in deliveries:
            cid = d["contest_id"]
            if cid not in contests_dict:
                contests_dict[cid] = {"contest": d["contest_name"], "platform": d["contest_platform"], "start": d["contest_start_utc"], "reminders": []}
            contests_dict[cid]["reminders"].append(d)

        embed = discord.Embed(
            title="Upcoming Contest Reminders",
            color=discord.Color.blue(),
            description="Reminders scheduled to be sent (sorted by soonest first):",
        )

        for i, (cid, data) in enumerate(list(contests_dict.items())[:5]):
            start_ts = int(data["start"].timestamp())
            platform_emoji = _PLATFORM_EMOJIS.get(data["platform"], "🏆")

            reminder_times = []
            for d in data["reminders"]:
                sched_ts = int(d["scheduled_for_utc"].timestamp())
                label = _NOTIF_LABELS.get(d["notification_type"], d["notification_type"])
                reminder_times.append(f"`{label}` (<t:{sched_ts}:R>)")

            val = (
                f"**Platform:** {platform_emoji} {data['platform'].title()}\n"
                f"**Starts:** <t:{start_ts}:F> (<t:{start_ts}:R>)\n"
                f"**Alerts:** {', '.join(reminder_times)}"
            )
            embed.add_field(name=data["contest"], value=val, inline=False)

        if len(contests_dict) > 5:
            embed.set_footer(text=f"And {len(contests_dict) - 5} more contests...")

        await interaction.followup.send(embed=embed)

    @group.command(name="enable", description="Admin-only: Enable contest reminders")
    @app_commands.default_permissions(administrator=True)
    async def enable(self, interaction: discord.Interaction) -> None:
        """Enable reminders."""
        await interaction.response.defer(ephemeral=True)
        success = await reminder_service.set_reminders_enabled(str(interaction.guild_id), True)
        if success:
            await interaction.followup.send("✅ Contest reminders are now **enabled**.")
        else:
            await interaction.followup.send("Please configure the bot with `/setup` first.")

    @group.command(name="disable", description="Admin-only: Disable contest reminders")
    @app_commands.default_permissions(administrator=True)
    async def disable(self, interaction: discord.Interaction) -> None:
        """Disable reminders."""
        await interaction.response.defer(ephemeral=True)
        success = await reminder_service.set_reminders_enabled(str(interaction.guild_id), False)
        if success:
            await interaction.followup.send("✅ Contest reminders are now **disabled**.")
        else:
            await interaction.followup.send("Please configure the bot with `/setup` first.")

    @group.command(name="test", description="Admin-only: Send a test reminder to the alert channel")
    @app_commands.default_permissions(administrator=True)
    async def test_reminder(self, interaction: discord.Interaction) -> None:
        """Test the reminder format in the configured channel."""
        await interaction.response.defer(ephemeral=True)

        settings = await guild_service.get_settings(str(interaction.guild_id))

        if not settings or not settings.contest_alert_channel_id:
            await interaction.followup.send(
                "Cannot send test: No contest alert channel is configured. Use `/setup contest-alert-channel`."
            )
            return

        guild = self.bot.get_guild(interaction.guild_id)
        if not guild:
            await interaction.followup.send("Internal error: Guild not found.")
            return

        channel = guild.get_channel(int(settings.contest_alert_channel_id))
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                "Cannot send test: The configured channel could not be found or is not a text channel."
            )
            return

        now_ts = int(datetime.now(UTC).timestamp())
        future_ts = now_ts + 600

        embed = discord.Embed(
            title="🟦 Test Contest — Codeforces Round (Div. 2)",
            url="https://codeforces.com/contests",
            color=discord.Color.blue(),
            description="⏰ Starting in **10 minutes**!",
        )
        embed.add_field(name="Platform", value="Codeforces", inline=True)
        embed.add_field(
            name="Start Time", value=f"<t:{future_ts}:F> (<t:{future_ts}:R>)", inline=True
        )
        embed.add_field(name="Duration", value="2h", inline=True)
        embed.add_field(name="Link", value="[Join Contest](https://codeforces.com/contests)", inline=False)
        embed.set_footer(text="The Citadel Contest Alerts")

        content = ""
        if settings.alert_role_id:
            content = f"<@&{settings.alert_role_id}>"

        try:
            await channel.send(content=content, embed=embed)
            await interaction.followup.send(
                f"✅ Test reminder sent to {channel.mention}!"
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "Failed to send test reminder: The bot does not have Send Messages permission in that channel."
            )
        except Exception as e:
            await interaction.followup.send(f"Failed to send test reminder: {e}")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Reminders(bot))
