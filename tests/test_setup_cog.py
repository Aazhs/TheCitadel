"""Tests for the setup cog — uses mocks, no real Discord connection needed."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest


class TestSetChannelValidation:
    """Test that channel subcommands validate bot permissions."""

    @pytest.mark.asyncio
    async def test_missing_send_messages_permission(self) -> None:
        """Bot lacks Send Messages → error response, no DB write."""
        from src.cogs.setup import Setup

        bot = MagicMock()
        bot.tree = MagicMock()
        cog = Setup(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111111111111111111
        interaction.user = MagicMock()
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        bot_member = MagicMock(spec=discord.Member)
        interaction.guild.me = bot_member

        channel = MagicMock(spec=discord.TextChannel)
        channel.mention = "#test-channel"
        channel.name = "test-channel"
        channel.id = 222222222222222222

        perms = MagicMock(spec=discord.Permissions)
        perms.view_channel = True
        perms.send_messages = False
        channel.permissions_for.return_value = perms

        # Wrap in an AppCommandChannel-like mock
        app_channel = MagicMock()
        app_channel.resolve.return_value = channel

        with patch("src.cogs.setup.gs_service") as mock_service:
            await cog._set_channel(interaction, app_channel, "onboarding_channel_id", "Onboarding")
            mock_service.update_channel.assert_not_called()

        interaction.followup.send.assert_called_once()
        call_args = interaction.followup.send.call_args
        assert "Send Messages" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_missing_view_channel_permission(self) -> None:
        """Bot lacks View Channel → error response."""
        from src.cogs.setup import Setup

        bot = MagicMock()
        bot.tree = MagicMock()
        cog = Setup(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111111111111111111
        interaction.user = MagicMock()
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        bot_member = MagicMock(spec=discord.Member)
        interaction.guild.me = bot_member

        channel = MagicMock(spec=discord.TextChannel)
        channel.mention = "#test-channel"

        perms = MagicMock(spec=discord.Permissions)
        perms.view_channel = False
        perms.send_messages = True
        channel.permissions_for.return_value = perms

        app_channel = MagicMock()
        app_channel.resolve.return_value = channel

        with patch("src.cogs.setup.gs_service") as mock_service:
            await cog._set_channel(interaction, app_channel, "onboarding_channel_id", "Onboarding")
            mock_service.update_channel.assert_not_called()

        call_args = interaction.followup.send.call_args
        assert "View Channel" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_valid_permissions_persists_channel(self) -> None:
        """Bot has correct permissions → DB write and success response."""
        from src.cogs.setup import Setup

        bot = MagicMock()
        bot.tree = MagicMock()
        cog = Setup(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111111111111111111
        interaction.user = MagicMock()
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        bot_member = MagicMock(spec=discord.Member)
        interaction.guild.me = bot_member

        channel = MagicMock(spec=discord.TextChannel)
        channel.mention = "#general"
        channel.name = "general"
        channel.id = 222222222222222222

        perms = MagicMock(spec=discord.Permissions)
        perms.view_channel = True
        perms.send_messages = True
        channel.permissions_for.return_value = perms

        app_channel = MagicMock()
        app_channel.resolve.return_value = channel

        with patch("src.cogs.setup.gs_service") as mock_service:
            mock_service.update_channel = AsyncMock()
            await cog._set_channel(interaction, app_channel, "onboarding_channel_id", "Onboarding")
            mock_service.update_channel.assert_called_once_with(
                str(interaction.guild.id), "onboarding_channel_id", str(channel.id)
            )

        call_args = interaction.followup.send.call_args
        assert "✅" in call_args.args[0]


class TestViewCommand:
    """Test /setup view."""

    @pytest.mark.asyncio
    async def test_view_no_config(self) -> None:
        """View with no saved settings → 'not configured' embed."""
        from src.cogs.setup import Setup

        bot = MagicMock()
        bot.tree = MagicMock()
        cog = Setup(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111111111111111111
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        with patch("src.cogs.setup.gs_service") as mock_service:
            mock_service.get_settings = AsyncMock(return_value=None)
            await cog._view(interaction)

        interaction.followup.send.assert_called_once()
        call_kwargs = interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert "No configuration" in embed.description

    @pytest.mark.asyncio
    async def test_view_with_config(self) -> None:
        """View with full settings → all fields displayed."""
        from src.cogs.setup import Setup
        from src.db.models import GuildSettings

        bot = MagicMock()
        bot.tree = MagicMock()
        cog = Setup(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111111111111111111
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        settings = GuildSettings(
            discord_guild_id="111111111111111111",
            onboarding_channel_id="222222222222222222",
            announcement_channel_id="333333333333333333",
            contest_alert_channel_id="444444444444444444",
            alert_role_id="555555555555555555",
        )

        with patch("src.cogs.setup.gs_service") as mock_service:
            mock_service.get_settings = AsyncMock(return_value=settings)
            await cog._view(interaction)

        call_kwargs = interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        # Should have 8 fields: 3 channels + role + timezone + auto_events + last_run + reminders
        assert len(embed.fields) == 8


class TestAlertRole:
    """Test /setup alert-role."""

    @pytest.mark.asyncio
    async def test_role_below_bot_no_warnings(self) -> None:
        """Role is below bot → success, no warnings."""
        from src.cogs.setup import Setup

        bot = MagicMock()
        bot.tree = MagicMock()
        cog = Setup(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111111111111111111
        interaction.user = MagicMock()
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        bot_member = MagicMock(spec=discord.Member)
        bot_top_role = MagicMock(spec=discord.Role)
        bot_top_role.name = "Bot Role"
        bot_top_role.__gt__ = lambda self, other: True
        bot_top_role.__le__ = lambda self, other: False
        bot_member.top_role = bot_top_role
        bot_member.guild_permissions = MagicMock()
        bot_member.guild_permissions.mention_everyone = True
        interaction.guild.me = bot_member

        role = MagicMock(spec=discord.Role)
        role.name = "Competitor"
        role.id = 666666666666666666
        role.mention = "@Competitor"
        role.mentionable = True

        with patch("src.cogs.setup.gs_service") as mock_service:
            mock_service.update_alert_role = AsyncMock()
            await cog._alert_role(interaction, role)
            mock_service.update_alert_role.assert_called_once()

        call_args = interaction.followup.send.call_args
        assert "✅" in call_args.args[0]
        assert "⚠️" not in call_args.args[0]

    @pytest.mark.asyncio
    async def test_role_above_bot_shows_warning(self) -> None:
        """Role is above/equal to bot → warning included but still persisted."""
        from src.cogs.setup import Setup

        bot = MagicMock()
        bot.tree = MagicMock()
        cog = Setup(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111111111111111111
        interaction.user = MagicMock()
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        bot_member = MagicMock(spec=discord.Member)
        bot_top_role = MagicMock(spec=discord.Role)
        bot_top_role.name = "Bot Role"
        bot_top_role.__gt__ = lambda self, other: False
        bot_top_role.__le__ = lambda self, other: True
        bot_member.top_role = bot_top_role
        bot_member.guild_permissions = MagicMock()
        bot_member.guild_permissions.mention_everyone = False
        interaction.guild.me = bot_member

        role = MagicMock(spec=discord.Role)
        role.name = "Admin"
        role.id = 666666666666666666
        role.mention = "@Admin"
        role.mentionable = False

        with patch("src.cogs.setup.gs_service") as mock_service:
            mock_service.update_alert_role = AsyncMock()
            await cog._alert_role(interaction, role)
            # Still persisted despite warnings
            mock_service.update_alert_role.assert_called_once()

        call_args = interaction.followup.send.call_args
        assert "⚠️" in call_args.args[0]


class TestResetCommand:
    """Test /setup reset."""

    @pytest.mark.asyncio
    async def test_reset_confirmed(self) -> None:
        """User clicks Yes → settings cleared."""
        from src.cogs.setup import ResetConfirmView, Setup

        bot = MagicMock()
        bot.tree = MagicMock()
        cog = Setup(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111111111111111111
        interaction.user = MagicMock()
        interaction.user.id = 999
        interaction.response = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        with (
            patch("src.cogs.setup.gs_service") as mock_service,
            patch("src.cogs.setup.ResetConfirmView") as mock_view_cls,
        ):
            view_instance = MagicMock(spec=ResetConfirmView)
            view_instance.confirmed = True
            view_instance.wait = AsyncMock()
            mock_view_cls.return_value = view_instance

            mock_service.reset_settings = AsyncMock()
            await cog._reset(interaction)

            mock_service.reset_settings.assert_called_once()

        interaction.edit_original_response.assert_called()
        call_kwargs = interaction.edit_original_response.call_args.kwargs
        assert "reset" in call_kwargs["content"].lower()

    @pytest.mark.asyncio
    async def test_reset_cancelled(self) -> None:
        """User clicks Cancel → no changes."""
        from src.cogs.setup import ResetConfirmView, Setup

        bot = MagicMock()
        bot.tree = MagicMock()
        cog = Setup(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111111111111111111
        interaction.user = MagicMock()
        interaction.user.id = 999
        interaction.response = AsyncMock()
        interaction.edit_original_response = AsyncMock()

        with (
            patch("src.cogs.setup.gs_service") as mock_service,
            patch("src.cogs.setup.ResetConfirmView") as mock_view_cls,
        ):
            view_instance = MagicMock(spec=ResetConfirmView)
            view_instance.confirmed = False
            view_instance.wait = AsyncMock()
            mock_view_cls.return_value = view_instance

            mock_service.reset_settings = AsyncMock()
            await cog._reset(interaction)

            mock_service.reset_settings.assert_not_called()

        call_kwargs = interaction.edit_original_response.call_args.kwargs
        assert "cancelled" in call_kwargs["content"].lower()
