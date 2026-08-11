"""Tests for the events cog."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord import app_commands


@pytest.mark.asyncio
class TestEventsCog:
    async def test_event_create(self) -> None:
        from src.cogs.events import Events
        from src.db.models import Event

        bot = MagicMock()
        cog = Events(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.user = MagicMock()
        interaction.user.id = 222
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 333

        event = Event(
            id=1,
            title="Test Event",
            status="draft",
            start_time_utc=MagicMock(),
            end_time_utc=MagicMock(),
        )
        mock_gs = MagicMock()
        mock_gs.timezone = "UTC"

        with (
            patch("src.cogs.events.event_service") as mock_service,
            patch("src.cogs.events.gs_service") as mock_gs_service,
        ):
            mock_gs_service.get_or_create = AsyncMock(return_value=mock_gs)
            mock_service.create_event = AsyncMock(return_value=event)
            await cog.event_create.callback(
                cog,
                interaction,
                "Test Event",
                app_commands.Choice(name="Codeforces", value="codeforces_contest"),
                "2026-08-01 10:00",
                "2026-08-01 12:00",
                "Desc",
                channel,
            )

            mock_service.create_event.assert_called_once()
            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args.args[0]
            assert "created" in args.lower()

    async def test_event_publish(self) -> None:
        from src.cogs.events import Events
        from src.db.models import Event

        bot = MagicMock()
        cog = Events(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        channel = AsyncMock(spec=discord.TextChannel)
        channel.send = AsyncMock(return_value=MagicMock(id=999))
        interaction.guild.get_channel = MagicMock(return_value=channel)

        event = Event(
            id=1,
            title="Test Event",
            status="published",
            announcement_channel_id="333",
            start_time_utc=MagicMock(),
            end_time_utc=MagicMock(),
        )

        with patch("src.cogs.events.event_service") as mock_service, \
             patch("src.cogs.events.gs_service") as mock_gs_service:
            mock_service.publish_event = AsyncMock(return_value=event)
            mock_service.update_announcement_message_id = AsyncMock()
            mock_gs_service.get_settings = AsyncMock(return_value=MagicMock(alert_role_id="12345"))
    
            await cog.event_publish.callback(cog, interaction, 1)

            channel.send.assert_called_once()
            mock_service.update_announcement_message_id.assert_called_once_with(1, "999")
            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args.args[0]
            assert "published and announced" in args.lower()

    async def test_event_cancel(self) -> None:
        from src.cogs.events import Events
        from src.db.models import Event

        bot = MagicMock()
        cog = Events(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        msg = AsyncMock(spec=discord.Message)
        msg.edit = AsyncMock()

        channel = AsyncMock(spec=discord.TextChannel)
        channel.fetch_message = AsyncMock(return_value=msg)
        interaction.guild.get_channel = MagicMock(return_value=channel)

        event = Event(
            id=1,
            title="Test Event",
            status="cancelled",
            announcement_channel_id="333",
            announcement_message_id="999",
            start_time_utc=MagicMock(),
            end_time_utc=MagicMock(),
        )

        with patch("src.cogs.events.event_service") as mock_service:
            mock_service.cancel_event = AsyncMock(return_value=event)

            await cog.event_cancel.callback(cog, interaction, 1)

            msg.edit.assert_called_once()
            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args.args[0]
            assert "cancelled" in args.lower()

    async def test_event_list(self) -> None:
        from src.cogs.events import Events
        from src.db.models import Event

        bot = MagicMock()
        cog = Events(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        event = Event(
            id=1,
            title="Test Event",
            status="active",
            event_type="codeforces_contest",
            start_time_utc=MagicMock(),
        )

        with patch("src.cogs.events.event_service") as mock_service:
            mock_service.list_events = AsyncMock(return_value=[event])

            await cog.event_list.callback(cog, interaction)

            interaction.followup.send.assert_called_once()
            kwargs = interaction.followup.send.call_args.kwargs
            assert "embed" in kwargs
            assert "Test Event" in kwargs["embed"].fields[0].name

    async def test_event_view(self) -> None:
        from src.cogs.events import Events
        from src.db.models import Event

        bot = MagicMock()
        cog = Events(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        event = Event(
            id=1,
            title="Test Event",
            status="active",
            event_type="codeforces_contest",
            start_time_utc=MagicMock(),
            end_time_utc=MagicMock(),
        )

        with patch("src.cogs.events.event_service") as mock_service:
            mock_service.get_event = AsyncMock(return_value=event)
            mock_service.get_registration_count = AsyncMock(return_value=10)

            await cog.event_view.callback(cog, interaction, 1)

            interaction.followup.send.assert_called_once()
            kwargs = interaction.followup.send.call_args.kwargs
            assert "embed" in kwargs
            # check that registered count is 10
            fields = kwargs["embed"].fields
            assert any(f.name == "Registered" and f.value == "10" for f in fields)


@pytest.mark.asyncio
class TestRegistration:
    async def test_register_happy_path(self) -> None:
        from src.cogs.events import Events

        bot = MagicMock()
        cog = Events(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.user = MagicMock()
        interaction.user.id = 222
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        with patch("src.cogs.events.event_service") as mock_service:
            mock_service.REQUIRE_CF_LINK_FOR_CF_EVENTS = False
            mock_service.register_for_event = AsyncMock()

            await cog.register.callback(cog, interaction, 1)

            mock_service.register_for_event.assert_called_once_with(1, "111", "222")
            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args.args[0]
            assert "registered" in args.lower()

    async def test_register_rejected_cancelled(self) -> None:
        from src.cogs.events import Events

        bot = MagicMock()
        cog = Events(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.user = MagicMock()
        interaction.user.id = 222
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        with patch("src.cogs.events.event_service") as mock_service:
            mock_service.REQUIRE_CF_LINK_FOR_CF_EVENTS = False
            mock_service.register_for_event = AsyncMock(
                side_effect=ValueError("Registration is not open")
            )

            await cog.register.callback(cog, interaction, 1)

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args.args[0]
            assert "Registration is not open" in args

    async def test_button_interaction(self) -> None:
        from src.cogs.events import DynamicRegisterButton

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.user = MagicMock()
        interaction.user.id = 222
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        button = DynamicRegisterButton(1)

        with patch("src.cogs.events.event_service") as mock_service:
            mock_service.REQUIRE_CF_LINK_FOR_CF_EVENTS = False
            mock_service.register_for_event = AsyncMock()
            with patch("src.cogs.events._update_event_message", new_callable=AsyncMock):
                await button.callback(interaction)

            mock_service.register_for_event.assert_called_once_with(1, "111", "222")
            interaction.response.defer.assert_called_once()
            interaction.followup.send.assert_called_once()
            kwargs = interaction.followup.send.call_args.kwargs
            assert kwargs.get("ephemeral") is True

    async def test_codeforces_event_requires_link(self) -> None:
        from src.cogs.events import Events
        from src.db.models import Event

        bot = MagicMock()
        cog = Events(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.user = MagicMock()
        interaction.user.id = 222
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        event = Event(id=1, event_type="codeforces_contest")

        with (
            patch("src.cogs.events.event_service") as mock_service,
            patch("src.cogs.events.la_service") as mock_la_service,
        ):
            mock_service.REQUIRE_CF_LINK_FOR_CF_EVENTS = True
            mock_service.get_event = AsyncMock(return_value=event)
            mock_la_service.get_member_accounts = AsyncMock(return_value=[])

            await cog.register.callback(cog, interaction, 1)

            interaction.followup.send.assert_called_once()
            args = interaction.followup.send.call_args.args[0]
            assert "link your codeforces account" in args.lower()
            mock_service.register_for_event.assert_not_called()

    async def test_non_codeforces_event_no_link_needed(self) -> None:
        from src.cogs.events import Events
        from src.db.models import Event

        bot = MagicMock()
        cog = Events(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.user = MagicMock()
        interaction.user.id = 222
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        event = Event(id=1, event_type="leetcode_contest")

        with (
            patch("src.cogs.events.event_service") as mock_service,
            patch("src.cogs.events.la_service"),
        ):
            mock_service.REQUIRE_CF_LINK_FOR_CF_EVENTS = True
            mock_service.get_event = AsyncMock(return_value=event)
            mock_service.register_for_event = AsyncMock()

            await cog.register.callback(cog, interaction, 1)

            mock_service.register_for_event.assert_called_once()

    async def test_my_events(self) -> None:
        from src.cogs.events import Events
        from src.db.models import Event

        bot = MagicMock()
        cog = Events(bot)

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = 111
        interaction.user = MagicMock()
        interaction.user.id = 222
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        event = Event(id=1, title="Test Event", status="active", start_time_utc=MagicMock())

        with patch("src.cogs.events.event_service") as mock_service:
            mock_service.get_user_events = AsyncMock(return_value=[event])

            await cog.my_events.callback(cog, interaction)

            interaction.followup.send.assert_called_once()
            kwargs = interaction.followup.send.call_args.kwargs
            assert "embed" in kwargs
            assert "Test Event" in kwargs["embed"].fields[0].name
