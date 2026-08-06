from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from src.cogs.contests import Contests
from src.db.models import Contest


@pytest.fixture
def cog():
    bot = MagicMock()
    return Contests(bot)


@pytest.fixture
def interaction():
    i = AsyncMock(spec=discord.Interaction)
    i.user = AsyncMock(spec=discord.Member)
    i.user.guild_permissions.administrator = True
    i.response = AsyncMock()
    i.response.defer = AsyncMock()
    i.followup = AsyncMock()
    i.followup.send = AsyncMock()
    return i


@pytest.mark.asyncio
@patch("src.cogs.contests.contest_service")
async def test_upcoming_no_contests(mock_service, cog, interaction):
    mock_service.get_upcoming_contests = AsyncMock(return_value=[])

    await cog.upcoming.callback(cog, interaction)

    interaction.response.defer.assert_called_once()
    interaction.followup.send.assert_called_once()
    args, _kwargs = interaction.followup.send.call_args
    assert "No upcoming contests" in args[0]


@pytest.mark.asyncio
@patch("src.cogs.contests.contest_service")
async def test_upcoming_with_contests(mock_service, cog, interaction):
    now = datetime.now(UTC)
    c1 = Contest(
        platform="codeforces",
        external_contest_id="101",
        name="Codeforces Round (Div. 2)",
        url="http://test",
        start_time_utc=now + timedelta(days=1),
        duration_seconds=7200,
        phase="BEFORE",
    )
    mock_service.get_upcoming_contests = AsyncMock(return_value=[c1])

    await cog.upcoming.callback(cog, interaction)

    interaction.response.defer.assert_called_once()
    interaction.followup.send.assert_called_once()
    _args, kwargs = interaction.followup.send.call_args
    embed = kwargs["embed"]

    assert embed.title == "Upcoming Contests"
    assert len(embed.fields) == 1
    assert embed.fields[0].name == "[Div. 2] Codeforces Round (Div. 2)"
    assert "2h" in embed.fields[0].value


@pytest.mark.asyncio
@patch("src.cogs.contests.cf_provider")
@patch("src.cogs.contests.contest_service")
async def test_refresh_contests(mock_service, mock_provider, cog, interaction):
    mock_provider.fetch_contests = AsyncMock(return_value=[MagicMock()])
    mock_service.sync_codeforces_contests = AsyncMock(return_value=(2, 1))

    await cog.refresh_codeforces.callback(cog, interaction)

    interaction.response.defer.assert_called_once_with(ephemeral=True)
    interaction.followup.send.assert_called_once()
    args, _kwargs = interaction.followup.send.call_args
    assert "Added **2**" in args[0]
    assert "updated **1**" in args[0]
