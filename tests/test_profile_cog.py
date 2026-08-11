"""Tests for the Profile cog."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import discord
import pytest

from src.cogs.profile import Profile
from src.db.models import LinkedAccount
from src.providers.codeforces import CodeforcesUser


@pytest.fixture
def cog():
    """Returns an instance of the Profile cog."""
    bot = AsyncMock(spec=discord.ext.commands.Bot)
    return Profile(bot)


@pytest.fixture
def interaction():
    """Returns a mock discord.Interaction."""
    mock = AsyncMock(spec=discord.Interaction)
    mock.guild = AsyncMock(spec=discord.Guild)
    mock.guild.id = 111
    mock.user = AsyncMock(spec=discord.Member)
    mock.user.id = 222
    mock.user.display_name = "TestUser"
    mock.response = AsyncMock(spec=discord.InteractionResponse)
    mock.response.is_done.return_value = False
    mock.followup = AsyncMock(spec=discord.Webhook)
    return mock


@pytest.mark.asyncio
@patch("src.cogs.profile.fetch_user")
@patch("src.cogs.profile.la_service")
@patch("src.db.engine.get_session_factory")
@patch("src.services.stats.recompute_member_stats", new_callable=AsyncMock)
async def test_link_codeforces_success(mock_recompute, mock_get_session, mock_la_service, mock_fetch_user, cog, interaction):
    """Test linking a Codeforces account successfully."""
    cf_user = CodeforcesUser(
        handle="tourist",
        rating=3900,
        max_rating=4000,
        rank="legendary grandmaster",
        max_rank="legendary grandmaster",
        title_photo=None,
        avatar=None,
    )
    mock_fetch_user.return_value = cf_user

    mock_account = LinkedAccount(handle="tourist", profile_url="http://test", validation_status="validated")
    mock_la_service.link_account = AsyncMock(return_value=mock_account)
    
    # Mock db session for recompute
    mock_session = AsyncMock()
    mock_get_session.return_value.return_value.__aenter__.return_value = mock_session

    await cog.link.callback(cog, interaction, platform="codeforces", handle="tourist")

    interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_la_service.link_account.assert_called_once_with(
        guild_id="111", 
        user_id="222", 
        platform="codeforces", 
        handle="tourist", 
        profile_url="https://codeforces.com/profile/tourist",
        validation_status="validated",
        current_rating=3900,
        max_rating=4000,
        global_rank=None,
        extra_data=None,
    )

    # Verify success embed was sent
    interaction.followup.send.assert_called_once()
    _, kwargs = interaction.followup.send.call_args
    assert "embed" in kwargs
    embed = kwargs["embed"]
    assert "Codeforces Account Linked" in embed.title


@pytest.mark.asyncio
@patch("src.cogs.profile.fetch_user")
async def test_link_codeforces_not_found(mock_fetch_user, cog, interaction):
    """Test linking an invalid Codeforces handle."""
    mock_fetch_user.return_value = None

    await cog.link.callback(cog, interaction, platform="codeforces", handle="invalid")

    interaction.response.defer.assert_called_once_with(ephemeral=True)

    # Verify error message was sent
    interaction.followup.send.assert_called_once()
    args, _kwargs = interaction.followup.send.call_args
    assert "Could not find a Codeforces user" in args[0]


@pytest.mark.asyncio
@patch("src.cogs.profile.la_service")
@patch("src.db.engine.get_session_factory")
@patch("src.services.stats.recompute_member_stats", new_callable=AsyncMock)
async def test_unlink_success(mock_recompute, mock_get_session, mock_la_service, cog, interaction):
    """Test unlinking an account successfully."""
    mock_la_service.unlink_account = AsyncMock(return_value=True)
    
    # Mock db session for recompute
    mock_session = AsyncMock()
    mock_get_session.return_value.return_value.__aenter__.return_value = mock_session

    await cog.unlink.callback(cog, interaction, platform="codeforces")

    interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_la_service.unlink_account.assert_called_once_with("111", "222", "codeforces")

    # Verify success message
    interaction.followup.send.assert_called_once()
    args, _kwargs = interaction.followup.send.call_args
    assert "unlinked" in args[0]


@pytest.mark.asyncio
@patch("src.cogs.profile.la_service")
async def test_unlink_not_found(mock_la_service, cog, interaction):
    """Test unlinking an account that doesn't exist."""
    mock_la_service.unlink_account = AsyncMock(return_value=False)

    await cog.unlink.callback(cog, interaction, platform="codeforces")

    # Verify error message
    interaction.followup.send.assert_called_once()
    args, _kwargs = interaction.followup.send.call_args
    assert "don't have a linked" in args[0]


@pytest.mark.asyncio
@patch("src.cogs.profile.la_service")
async def test_my_profile_with_accounts(mock_la_service, cog, interaction):
    """Test viewing own profile with linked accounts."""
    account = LinkedAccount(
        platform="codeforces",
        handle="tourist",
        profile_url="http://test",
        current_rating=3900,
    )
    mock_la_service.get_member_accounts = AsyncMock(return_value=[account])

    await cog.my_profile.callback(cog, interaction)

    interaction.response.defer.assert_called_once_with(ephemeral=True)
    mock_la_service.get_member_accounts.assert_called_once_with("111", "222")

    # Verify embed
    interaction.followup.send.assert_called_once()
    _, kwargs = interaction.followup.send.call_args
    embed = kwargs["embed"]
    assert "tourist" in embed.fields[0].value
    assert "3900" in embed.fields[0].value


@pytest.mark.asyncio
@patch("src.cogs.profile.la_service")
async def test_profile_no_accounts(mock_la_service, cog, interaction):
    """Test viewing a profile with no linked accounts."""
    mock_la_service.get_member_accounts = AsyncMock(return_value=[])

    target = AsyncMock(spec=discord.Member)
    target.id = 333
    target.display_name = "TargetUser"

    await cog.profile.callback(cog, interaction, member=target)

    interaction.response.defer.assert_called_once_with(ephemeral=False)

    # Verify embed
    interaction.followup.send.assert_called_once()
    _, kwargs = interaction.followup.send.call_args
    embed = kwargs["embed"]
    assert "No linked accounts found." in embed.description
