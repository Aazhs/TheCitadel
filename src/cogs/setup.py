"""Setup cog — admin-only guild configuration commands."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.services import guild_settings as gs_service

logger = logging.getLogger("arena.cogs.setup")


# ── Confirmation view for /setup reset ────────────────────────────────


class ResetConfirmView(discord.ui.View):
    """Yes / Cancel buttons for /setup reset."""

    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=60)
        self.author_id = author_id
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the original command invoker can press the buttons."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "⛔ Only the admin who ran this command can confirm.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Yes, reset", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[type-arg]
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[type-arg]
        self.confirmed = False
        self.stop()
        await interaction.response.defer()


# ── Setup command group ───────────────────────────────────────────────


class SetupGroup(app_commands.Group):
    """Admin commands for configuring The Citadel in this server."""

    def __init__(self) -> None:
        super().__init__(
            name="setup",
            description="Configure The Citadel for this server (admin only)",
            guild_only=True,
            default_permissions=discord.Permissions(administrator=True),
        )


class Setup(commands.Cog):
    """Server configuration cog."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.setup_group = SetupGroup()

        # Register subcommands
        self.setup_group.command(
            name="onboarding-channel",
            description="Set the channel for new member welcome messages",
        )(self._onboarding_channel)

        self.setup_group.command(
            name="announcement-channel",
            description="Set the channel for bot announcements",
        )(self._announcement_channel)

        self.setup_group.command(
            name="contest-alert-channel",
            description="Set the channel for contest reminders",
        )(self._contest_alert_channel)

        self.setup_group.command(
            name="alert-role",
            description="Set the role to ping for contest alerts",
        )(self._alert_role)

        self.setup_group.command(
            name="view",
            description="View current server configuration",
        )(self._view)

        self.setup_group.command(
            name="reset",
            description="Clear all Citadel channel/role configuration",
        )(self._reset)

        # Add the group to the bot's command tree
        bot.tree.add_command(self.setup_group)

    async def cog_unload(self) -> None:
        """Remove the command group when the cog unloads."""
        self.bot.tree.remove_command(self.setup_group.name)

    # ── channel subcommands ───────────────────────────────────────────

    async def _onboarding_channel(
        self, interaction: discord.Interaction, channel: app_commands.AppCommandChannel
    ) -> None:
        await self._set_channel(interaction, channel, "onboarding_channel_id", "Onboarding")

    async def _announcement_channel(
        self, interaction: discord.Interaction, channel: app_commands.AppCommandChannel
    ) -> None:
        await self._set_channel(interaction, channel, "announcement_channel_id", "Announcement")

    async def _contest_alert_channel(
        self, interaction: discord.Interaction, channel: app_commands.AppCommandChannel
    ) -> None:
        await self._set_channel(interaction, channel, "contest_alert_channel_id", "Contest Alert")

    async def _set_channel(
        self,
        interaction: discord.Interaction,
        channel: app_commands.AppCommandChannel,
        field: str,
        label: str,
    ) -> None:
        """Validate bot permissions in the channel, persist, and respond."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        bot_member = interaction.guild.me

        # Resolve from cache first, fall back to API fetch
        resolved = channel.resolve() or interaction.guild.get_channel(channel.id)
        if resolved is None:
            try:
                resolved = await interaction.guild.fetch_channel(channel.id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                # Can't resolve — save the channel ID anyway and let the user know
                await gs_service.update_channel(str(interaction.guild.id), field, str(channel.id))
                logger.warning(
                    "Could not resolve channel %s in guild %s — saved anyway",
                    channel.id,
                    interaction.guild.id,
                )
                await interaction.followup.send(
                    f"✅ **{label} channel** set to <#{channel.id}>\n\n"
                    f"⚠️ I couldn't verify my permissions in that channel. "
                    f"Please make sure I have **View Channel** and **Send Messages**.",
                    ephemeral=True,
                )
                return

        perms = resolved.permissions_for(bot_member)
        missing: list[str] = []
        if not perms.view_channel:
            missing.append("View Channel")
        if not perms.send_messages:
            missing.append("Send Messages")

        if missing:
            await interaction.followup.send(
                f"❌ I'm missing **{', '.join(missing)}** permission(s) in {resolved.mention}. "
                f"Please fix my permissions and try again.",
                ephemeral=True,
            )
            return

        await gs_service.update_channel(str(interaction.guild.id), field, str(resolved.id))

        logger.info(
            "%s set %s to #%s (%s) in guild %s",
            interaction.user,
            label,
            resolved.name,
            resolved.id,
            interaction.guild.id,
        )
        await interaction.followup.send(
            f"✅ **{label} channel** set to {resolved.mention}",
            ephemeral=True,
        )

    # ── alert role ────────────────────────────────────────────────────

    async def _alert_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        """Validate role hierarchy and persist the alert role."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)
        bot_member = interaction.guild.me

        warnings: list[str] = []

        # Check hierarchy
        if bot_member.top_role <= role:
            warnings.append(
                f"⚠️ My highest role (**{bot_member.top_role.name}**) is not above "
                f"**{role.name}**. I may not be able to mention this role."
            )

        # Check mentionability
        if not role.mentionable:
            bot_perms = bot_member.guild_permissions
            if not bot_perms.mention_everyone:
                warnings.append(
                    f"⚠️ **{role.name}** is not mentionable and I don't have "
                    f"**Mention Everyone** permission. I won't be able to ping this role."
                )

        await gs_service.update_alert_role(str(interaction.guild.id), str(role.id))

        msg = f"✅ **Alert role** set to {role.mention}"
        if warnings:
            msg += "\n\n" + "\n".join(warnings)

        logger.info(
            "%s set alert_role to @%s (%s) in guild %s",
            interaction.user,
            role.name,
            role.id,
            interaction.guild.id,
        )
        await interaction.followup.send(msg, ephemeral=True)

    # ── view ──────────────────────────────────────────────────────────

    async def _view(self, interaction: discord.Interaction) -> None:
        """Show current guild configuration."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        settings = await gs_service.get_settings(str(interaction.guild.id))

        embed = discord.Embed(
            title="⚙️ The Citadel — Server Configuration",
            color=discord.Color.blurple(),
        )

        if settings is None:
            embed.description = (
                "No configuration found for this server.\nUse `/setup` subcommands to get started."
            )
        else:
            embed.add_field(
                name="Onboarding Channel",
                value=f"<#{settings.onboarding_channel_id}>"
                if settings.onboarding_channel_id
                else "*Not set*",
                inline=True,
            )
            embed.add_field(
                name="Announcement Channel",
                value=f"<#{settings.announcement_channel_id}>"
                if settings.announcement_channel_id
                else "*Not set*",
                inline=True,
            )
            embed.add_field(
                name="Contest Alert Channel",
                value=f"<#{settings.contest_alert_channel_id}>"
                if settings.contest_alert_channel_id
                else "*Not set*",
                inline=True,
            )
            embed.add_field(
                name="Alert Role",
                value=f"<@&{settings.alert_role_id}>" if settings.alert_role_id else "*Not set*",
                inline=True,
            )
            embed.add_field(
                name="Timezone",
                value=settings.timezone,
                inline=True,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── reset ─────────────────────────────────────────────────────────

    async def _reset(self, interaction: discord.Interaction) -> None:
        """Clear all channel/role configuration with a confirmation step."""
        assert interaction.guild is not None

        view = ResetConfirmView(author_id=interaction.user.id)

        await interaction.response.send_message(
            "🗑️ **Are you sure you want to reset all Citadel configuration?**\n\n"
            "This will clear:\n"
            "• Onboarding channel\n"
            "• Announcement channel\n"
            "• Contest alert channel\n"
            "• Alert role\n\n"
            "User profiles and event data will **not** be deleted.",
            view=view,
            ephemeral=True,
        )

        await view.wait()

        if view.confirmed is True:
            await gs_service.reset_settings(str(interaction.guild.id))
            logger.info(
                "%s reset guild_settings for guild %s",
                interaction.user,
                interaction.guild.id,
            )
            await interaction.edit_original_response(
                content="✅ All Citadel configuration has been reset.",
                view=None,
            )
        elif view.confirmed is False:
            await interaction.edit_original_response(
                content="❌ Reset cancelled.",
                view=None,
            )
        else:
            # Timed out
            await interaction.edit_original_response(
                content="⏰ Reset timed out — no changes were made.",
                view=None,
            )


async def setup(bot: commands.Bot) -> None:
    """Load the Setup cog."""
    await bot.add_cog(Setup(bot))
    logger.info("Setup cog loaded")
