from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.cogs.reminders import Reminders
from src.db.models import GuildSettings
from src.services.reminders import DeliveryInfo


def _make_delivery_info(**kwargs) -> DeliveryInfo:
    """Build a DeliveryInfo with sensible defaults for tests."""
    defaults = dict(
        id=1,
        notification_type="10m",
        scheduled_for_utc=datetime.now(UTC),
        guild_id="123",
        channel_id="456",
        alert_role_id="789",
        contest_id=1,
        contest_name="C1",
        contest_url="https://codeforces.com/contest/1",
        contest_platform="codeforces",
        contest_start_utc=datetime.now(UTC) + timedelta(minutes=10),
        contest_duration_seconds=7200,
    )
    defaults.update(kwargs)
    return DeliveryInfo(**defaults)


@pytest.fixture
def cog():
    bot = MagicMock()
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
    settings = GuildSettings(
        reminders_enabled=True, contest_alert_channel_id="123", alert_role_id="456"
    )
    mock_guild_service.get_settings = AsyncMock(return_value=settings)

    await cog.status.callback(cog, interaction)

    interaction.followup.send.assert_called_once()
    _args, kwargs = interaction.followup.send.call_args
    embed = kwargs["embed"]
    assert embed.title == "Contest Reminders Status"
    assert embed.fields[0].name == "Enabled"
    # Updated: the cog now shows "✅ Yes" / "❌ No"
    assert "Yes" in embed.fields[0].value


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
    now = datetime.now(UTC)
    # The cog now receives plain dicts from the service
    delivery = {
        "id": 1,
        "notification_type": "24h",
        "scheduled_for_utc": now,
        "contest_id": 1,
        "contest_name": "C1",
        "contest_platform": "codeforces",
        "contest_start_utc": now + timedelta(hours=24),
    }
    mock_reminder_service.get_pending_deliveries_for_guild = AsyncMock(return_value=[delivery])

    await cog.list_reminders.callback(cog, interaction)

    interaction.followup.send.assert_called_once()
    _args, kwargs = interaction.followup.send.call_args
    embed = kwargs["embed"]
    assert embed.title == "Upcoming Contest Reminders"
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "C1"
    # Should show human-friendly label "24 hours"
    assert "24 hours" in embed.fields[0].value


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
    """When channel_id is None, mark delivery as FAILED."""
    mock_reminder_service.schedule_missing_deliveries = AsyncMock()
    delivery = _make_delivery_info(channel_id=None)
    mock_reminder_service.get_due_deliveries = AsyncMock(return_value=[delivery])
    mock_reminder_service.mark_delivery_status = AsyncMock()

    await cog.deliver_reminders_loop()

    mock_reminder_service.mark_delivery_status.assert_called_once_with(
        1, "FAILED", error="No alert channel configured"
    )


@pytest.mark.asyncio
@patch("src.cogs.reminders.reminder_service")
async def test_deliver_reminders_loop_success(mock_reminder_service, cog):
    """When all conditions met, send the embed and mark SENT."""
    mock_reminder_service.schedule_missing_deliveries = AsyncMock()
    delivery = _make_delivery_info(
        id=1,
        notification_type="10m",
        guild_id="123",
        channel_id="456",
        alert_role_id="789",
        contest_name="C1",
        contest_platform="codeforces",
        contest_url="https://codeforces.com/contest/1",
        contest_duration_seconds=7200,
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
    assert "C1" in kwargs["embed"].title

    mock_reminder_service.mark_delivery_status.assert_called_once()
    call_args, call_kwargs = mock_reminder_service.mark_delivery_status.call_args
    assert call_args[0] == 1
    assert call_args[1] == "SENT"
    assert call_kwargs["message_id"] == "999"
