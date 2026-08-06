"""Tests for the onboarding cog — uses mocks, no real Discord connection needed."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.db.models import GuildSettings


class TestOnMemberJoin:
    """Tests for the on_member_join listener."""

    @pytest.mark.asyncio
    async def test_welcome_message_sent_when_configured(self) -> None:
        """Configured onboarding channel → welcome embed sent."""
        from src.cogs.onboarding import Onboarding

        bot = MagicMock()
        cog = Onboarding(bot)

        member = MagicMock(spec=discord.Member)
        member.mention = "<@123>"
        member.display_avatar = MagicMock()
        member.display_avatar.url = "https://example.com/avatar.png"

        guild = MagicMock(spec=discord.Guild)
        guild.name = "The Citadel"
        guild.id = 111111111111111111
        guild.icon = MagicMock()
        guild.icon.url = "https://example.com/icon.png"
        member.guild = guild

        channel = MagicMock(spec=discord.TextChannel)
        channel.name = "welcome"
        channel.id = 222222222222222222
        channel.send = AsyncMock()

        perms = MagicMock(spec=discord.Permissions)
        perms.send_messages = True
        channel.permissions_for.return_value = perms

        guild.me = MagicMock(spec=discord.Member)
        guild.get_channel.return_value = channel

        settings = GuildSettings(
            discord_guild_id="111111111111111111",
            onboarding_channel_id="222222222222222222",
        )

        with patch("src.cogs.onboarding.gs_service") as mock_service:
            mock_service.get_settings = AsyncMock(return_value=settings)
            await cog.on_member_join(member)

        channel.send.assert_called_once()
        call_kwargs = channel.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert "Welcome" in embed.title
        assert member.mention in embed.description

    @pytest.mark.asyncio
    async def test_no_config_logs_warning(self) -> None:
        """No guild settings → no message, warning logged."""
        from src.cogs.onboarding import Onboarding

        bot = MagicMock()
        cog = Onboarding(bot)

        member = MagicMock(spec=discord.Member)
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        guild.id = 111111111111111111
        member.guild = guild

        with (
            patch("src.cogs.onboarding.gs_service") as mock_service,
            patch("src.cogs.onboarding.logger") as mock_logger,
        ):
            mock_service.get_settings = AsyncMock(return_value=None)
            await cog.on_member_join(member)

            mock_logger.warning.assert_called_once()
            assert "onboarding channel" in mock_logger.warning.call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_no_onboarding_channel_set_logs_warning(self) -> None:
        """Guild settings exist but onboarding_channel_id is None → warning."""
        from src.cogs.onboarding import Onboarding

        bot = MagicMock()
        cog = Onboarding(bot)

        member = MagicMock(spec=discord.Member)
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        guild.id = 111111111111111111
        member.guild = guild

        settings = GuildSettings(
            discord_guild_id="111111111111111111",
            onboarding_channel_id=None,
        )

        with (
            patch("src.cogs.onboarding.gs_service") as mock_service,
            patch("src.cogs.onboarding.logger") as mock_logger,
        ):
            mock_service.get_settings = AsyncMock(return_value=settings)
            await cog.on_member_join(member)

            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_deleted_channel_logs_warning(self) -> None:
        """Channel ID is set but the channel no longer exists → warning, no crash."""
        from src.cogs.onboarding import Onboarding

        bot = MagicMock()
        cog = Onboarding(bot)

        member = MagicMock(spec=discord.Member)
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        guild.id = 111111111111111111
        guild.get_channel.return_value = None
        member.guild = guild

        settings = GuildSettings(
            discord_guild_id="111111111111111111",
            onboarding_channel_id="222222222222222222",
        )

        with (
            patch("src.cogs.onboarding.gs_service") as mock_service,
            patch("src.cogs.onboarding.logger") as mock_logger,
        ):
            mock_service.get_settings = AsyncMock(return_value=settings)
            await cog.on_member_join(member)

            mock_logger.warning.assert_called_once()
            assert "no longer exists" in mock_logger.warning.call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_no_send_permission_logs_warning(self) -> None:
        """Channel exists but bot can't send → warning, no crash."""
        from src.cogs.onboarding import Onboarding

        bot = MagicMock()
        cog = Onboarding(bot)

        member = MagicMock(spec=discord.Member)
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        guild.id = 111111111111111111
        guild.me = MagicMock(spec=discord.Member)
        member.guild = guild

        channel = MagicMock(spec=discord.TextChannel)
        channel.name = "welcome"
        channel.id = 222222222222222222
        perms = MagicMock(spec=discord.Permissions)
        perms.send_messages = False
        channel.permissions_for.return_value = perms
        guild.get_channel.return_value = channel

        settings = GuildSettings(
            discord_guild_id="111111111111111111",
            onboarding_channel_id="222222222222222222",
        )

        with (
            patch("src.cogs.onboarding.gs_service") as mock_service,
            patch("src.cogs.onboarding.logger") as mock_logger,
        ):
            mock_service.get_settings = AsyncMock(return_value=settings)
            await cog.on_member_join(member)

            mock_logger.warning.assert_called_once()
            assert "cannot send" in mock_logger.warning.call_args.args[0].lower()


class TestStartCommand:
    """Tests for the /start command."""

    @pytest.mark.asyncio
    async def test_start_returns_ephemeral_embed(self) -> None:
        """/start responds with an ephemeral embed listing next steps."""
        from src.cogs.onboarding import Onboarding

        bot = MagicMock()
        cog = Onboarding(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild_id = 111111111111111111
        interaction.user = MagicMock()
        interaction.response = AsyncMock()

        await cog.start.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs["ephemeral"] is True

        embed = call_kwargs["embed"]
        assert "Citadel" in embed.title
        # Should have 3 fields: profiles, alerts, upcoming
        assert len(embed.fields) == 3
        # Each field should mention "coming soon"
        for field in embed.fields:
            assert "coming soon" in field.value.lower()
