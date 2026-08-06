from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.cogs.reminders import Reminders
from src.db.models import Contest, GuildSettings, NotificationDelivery


@pytest.fixture
def cog():
    bot = MagicMock()
    # Mock bot methods
    bot.get_guild = MagicMock()
    return Reminders(bot)

@pytest.fixture
def interaction():
    i = AsyncMock(spec=discord.Interaction)
    i.user = AsyncMock(spec=discord.Member)
    i.user.guild_permissions.administrator = True
    i.response = AsyncMock()
    i.response.send_message = AsyncMock()
    i.response.defer = AsyncMock()
    i.followup = AsyncMock()
    i.followup.send = AsyncMock()
    return i

@pytest.mark.asyncio
@patch("src.cogs.reminders.guild_service")
async def test_status_command_not_configured(mock_guild_service, cog, interaction):
    mock_guild_service.get_settings = AsyncMock(return_value=None)

    await cog.status.callback(cog, interaction)

    interaction.followup.send.assert_called_once()
    _args, kwargs = interaction.followup.send.call_args
    embed = kwargs["embed"]
    assert "not been configured yet" in embed.description

@pytest.mark.asyncio
@patch("src.cogs.reminders.guild_service")
async def test_status_command_configured(mock_guild_service, cog, interaction):
    settings = GuildSettings(reminders_enabled=True, contest_alert_channel_id="123", alert_role_id="456")
    mock_guild_service.get_settings = AsyncMock(return_value=settings)

    await cog.status.callback(cog, interaction)

    interaction.followup.send.assert_called_once()
    _args, kwargs = interaction.followup.send.call_args
    embed = kwargs["embed"]
    assert embed.title == "Contest Reminders Status"
    assert embed.fields[0].name == "Enabled"
    assert embed.fields[0].value == "Yes"

@pytest.mark.asyncio
@patch("src.cogs.reminders.reminder_service")
async def test_enable_command(mock_reminder_service, cog, interaction):
    mock_reminder_service.set_reminders_enabled = AsyncMock(return_value=True)

    await cog.enable.callback(cog, interaction)

    interaction.followup.send.assert_called_once()
    args, _kwargs = interaction.followup.send.call_args
    assert "enabled" in args[0]

@pytest.mark.asyncio
@patch("src.cogs.reminders.reminder_service")
async def test_list_reminders_empty(mock_reminder_service, cog, interaction):
    mock_reminder_service.get_pending_deliveries_for_guild = AsyncMock(return_value=[])
    
    await cog.list_reminders.callback(cog, interaction)
    
    interaction.followup.send.assert_called_once()
    args, _kwargs = interaction.followup.send.call_args
    assert "no upcoming reminders" in args[0]

@pytest.mark.asyncio
@patch("src.cogs.reminders.reminder_service")
async def test_list_reminders_with_deliveries(mock_reminder_service, cog, interaction):
    delivery = NotificationDelivery(
        id=1,
        notification_type="24h",
        scheduled_for_utc=datetime.now(UTC),
        contest_id=1,
        contest=Contest(name="C1", platform="codeforces", start_time_utc=datetime.now(UTC))
    )
    mock_reminder_service.get_pending_deliveries_for_guild = AsyncMock(return_value=[delivery])
    
    await cog.list_reminders.callback(cog, interaction)
    
    interaction.followup.send.assert_called_once()
    _args, kwargs = interaction.followup.send.call_args
    embed = kwargs["embed"]
    assert embed.title == "Upcoming Contest Reminders"
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "C1"
    assert "24h" in embed.fields[0].value

@pytest.mark.asyncio
@patch("src.cogs.reminders.reminder_service")
async def test_deliver_reminders_loop_no_deliveries(mock_reminder_service, cog):
    mock_reminder_service.schedule_missing_deliveries = AsyncMock(return_value=0)
    mock_reminder_service.get_due_deliveries = AsyncMock(return_value=[])

    await cog.deliver_reminders_loop()

    mock_reminder_service.schedule_missing_deliveries.assert_called_once()
    mock_reminder_service.get_due_deliveries.assert_called_once()
    mock_reminder_service.mark_delivery_status.assert_not_called()

@pytest.mark.asyncio
@patch("src.cogs.reminders.reminder_service")
async def test_deliver_reminders_loop_missing_channel_id(mock_reminder_service, cog):
    mock_reminder_service.schedule_missing_deliveries = AsyncMock()
    delivery = NotificationDelivery(
        id=1,
        guild_settings=GuildSettings(discord_guild_id="123", contest_alert_channel_id=None),
        contest=Contest(name="C1", start_time_utc=datetime.now(UTC))
    )
    mock_reminder_service.get_due_deliveries = AsyncMock(return_value=[delivery])
    mock_reminder_service.mark_delivery_status = AsyncMock()

    await cog.deliver_reminders_loop()

    mock_reminder_service.mark_delivery_status.assert_called_once_with(1, "FAILED", error="No alert channel configured")

@pytest.mark.asyncio
@patch("src.cogs.reminders.reminder_service")
async def test_deliver_reminders_loop_success(mock_reminder_service, cog):
    mock_reminder_service.schedule_missing_deliveries = AsyncMock()
    delivery = NotificationDelivery(
        id=1,
        notification_type="10m",
        guild_settings=GuildSettings(discord_guild_id="123", contest_alert_channel_id="456", alert_role_id="789"),
        contest=Contest(name="C1", platform="codeforces", start_time_utc=datetime.now(UTC), url="http", duration_seconds=7200)
    )
    mock_reminder_service.get_due_deliveries = AsyncMock(return_value=[delivery])
    mock_reminder_service.mark_delivery_status = AsyncMock()

    mock_guild = MagicMock()
    mock_channel = AsyncMock(spec=discord.TextChannel)
    mock_message = MagicMock(id=999)
    mock_channel.send.return_value = mock_message
    mock_guild.get_channel.return_value = mock_channel
    cog.bot.get_guild.return_value = mock_guild

    await cog.deliver_reminders_loop()

    mock_channel.send.assert_called_once()
    args, kwargs = mock_channel.send.call_args
    assert kwargs["content"] == "<@&789>"
    assert kwargs["embed"].title == "C1"

    mock_reminder_service.mark_delivery_status.assert_called_once()
    args, kwargs = mock_reminder_service.mark_delivery_status.call_args
    assert args[0] == 1
    assert args[1] == "SENT"
    assert kwargs["message_id"] == "999"
