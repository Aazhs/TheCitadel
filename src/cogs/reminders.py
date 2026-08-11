"""Reminders cog for scheduling and delivering contest alerts."""

import logging
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.services import guild_settings as guild_service
from src.services import reminders as reminder_service

logger = logging.getLogger("arena.cogs.reminders")


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

            # Second, fetch any deliveries that are due right now
            due_deliveries = await reminder_service.get_due_deliveries()
            if not due_deliveries:
                return

            now = datetime.now(UTC)

            for delivery in due_deliveries:
                guild_id = delivery.guild_settings.discord_guild_id
                channel_id = delivery.guild_settings.contest_alert_channel_id

                if not channel_id:
                    await reminder_service.mark_delivery_status(
                        delivery.id, "FAILED", error="No alert channel configured"
                    )
                    continue

                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    await reminder_service.mark_delivery_status(
                        delivery.id, "FAILED", error="Guild not found"
                    )
                    continue

                channel = guild.get_channel(int(channel_id))
                if not channel or not isinstance(channel, discord.TextChannel):
                    await reminder_service.mark_delivery_status(
                        delivery.id, "FAILED", error="Alert channel not found or not a text channel"
                    )
                    continue

                # Build the embed
                c = delivery.contest
                start_ts = int(c.start_time_utc.timestamp())
                embed = discord.Embed(
                    title=c.name,
                    url=c.url,
                    color=discord.Color.brand_red(),
                    description=f"Starting in **{delivery.notification_type}**!",
                )
                embed.add_field(name="Platform", value=c.platform.title(), inline=True)
                embed.add_field(
                    name="Start Time", value=f"<t:{start_ts}:F> (<t:{start_ts}:R>)", inline=True
                )
                if c.duration_seconds:
                    duration_hrs = c.duration_seconds / 3600
                    embed.add_field(name="Duration", value=f"{duration_hrs:g} hours", inline=True)

                # Format ping
                content = ""
                role_id = delivery.guild_settings.alert_role_id
                if role_id:
                    content = f"<@&{role_id}>"

                try:
                    msg = await channel.send(content=content, embed=embed)
                    await reminder_service.mark_delivery_status(
                        delivery.id, "SENT", sent_at=now, message_id=str(msg.id)
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
            name="Enabled", value="Yes" if settings.reminders_enabled else "No", inline=False
        )

        if settings.contest_alert_channel_id:
            embed.add_field(
                name="Alert Channel", value=f"<#{settings.contest_alert_channel_id}>", inline=True
            )
        else:
            embed.add_field(name="Alert Channel", value="Not set", inline=True)

        if settings.alert_role_id:
            embed.add_field(name="Alert Role", value=f"<@&{settings.alert_role_id}>", inline=True)
        else:
            embed.add_field(name="Alert Role", value="Not set", inline=True)

        await interaction.followup.send(embed=embed)

    @group.command(name="list", description="List upcoming scheduled contest reminders")
    async def list_reminders(self, interaction: discord.Interaction) -> None:
        """List upcoming reminders for this server."""
        await interaction.response.defer(ephemeral=True)

        deliveries = await reminder_service.get_pending_deliveries_for_guild(
            str(interaction.guild_id)
        )

        if not deliveries:
            await interaction.followup.send(
                "There are currently no upcoming reminders scheduled for this server."
            )
            return

        # Group deliveries by contest
        # We can just show the next 5 contests to avoid hitting embed limits
        contests_dict = {}
        for d in deliveries:
            if d.contest_id not in contests_dict:
                contests_dict[d.contest_id] = {"contest": d.contest, "reminders": []}
            contests_dict[d.contest_id]["reminders"].append(d)

        embed = discord.Embed(
            title="Upcoming Contest Reminders",
            color=discord.Color.blue(),
            description="Here are the upcoming reminders scheduled to be sent:",
        )

        for i, (cid, data) in enumerate(list(contests_dict.items())[:5]):
            c = data["contest"]
            start_ts = int(c.start_time_utc.timestamp())

            # Format reminders
            reminder_times = []
            for d in data["reminders"]:
                sched_ts = int(d.scheduled_for_utc.timestamp())
                reminder_times.append(f"`{d.notification_type}` (<t:{sched_ts}:R>)")

            val = f"**Platform:** {c.platform.title()}\n**Starts:** <t:{start_ts}:F> (<t:{start_ts}:R>)\n**Scheduled Alerts:** {', '.join(reminder_times)}"
            embed.add_field(name=c.name, value=val, inline=False)

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
            await interaction.followup.send("Contest reminders are now **enabled**.")
        else:
            await interaction.followup.send("Please configure the bot with `/setup` first.")

    @group.command(name="disable", description="Admin-only: Disable contest reminders")
    @app_commands.default_permissions(administrator=True)
    async def disable(self, interaction: discord.Interaction) -> None:
        """Disable reminders."""
        await interaction.response.defer(ephemeral=True)
        success = await reminder_service.set_reminders_enabled(str(interaction.guild_id), False)
        if success:
            await interaction.followup.send("Contest reminders are now **disabled**.")
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

        embed = discord.Embed(
            title="Test Contest (Div. 1)",
            url="https://codeforces.com/contests",
            color=discord.Color.brand_red(),
            description="Starting in **10m**!",
        )
        embed.add_field(name="Platform", value="Codeforces", inline=True)

        now_ts = int(datetime.now(UTC).timestamp())
        future_ts = now_ts + 600

        embed.add_field(
            name="Start Time", value=f"<t:{future_ts}:F> (<t:{future_ts}:R>)", inline=True
        )
        embed.add_field(name="Duration", value="2 hours", inline=True)

        content = ""
        if settings.alert_role_id:
            content = f"<@&{settings.alert_role_id}>"

        try:
            await channel.send(content=content, embed=embed)
            await interaction.followup.send("Test reminder sent successfully!")
        except discord.Forbidden:
            await interaction.followup.send(
                "Failed to send test reminder: The bot does not have Send Messages permission in that channel."
            )
        except Exception as e:
            await interaction.followup.send(f"Failed to send test reminder: {e}")


async def setup(bot: commands.Bot) -> None:
    """Add the cog to the bot."""
    await bot.add_cog(Reminders(bot))
