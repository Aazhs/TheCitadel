"""Tests for the guild_settings service layer.

Uses a mocked session factory so no real database is needed.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.db.base import Base
from src.db.models import GuildSettings
from src.services import guild_settings as gs_service

# ── Helpers ────────────────────────────────────────────────────────────


def _make_sync_db():
    """Create an in-memory SQLite engine and return (engine, session)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


# For the async service tests we mock get_session_factory to return
# a mock that produces an AsyncMock session wrapping a real sync session.
# This is simpler than standing up a full async engine for unit tests.


class FakeAsyncSession:
    """Wraps a sync SQLAlchemy Session with an async-like interface.

    Good enough for testing the service layer without a real async engine.
    """

    def __init__(self, sync_session: Session) -> None:
        self._session = sync_session

    async def execute(self, stmt):
        return self._session.execute(stmt)

    def add(self, obj):
        self._session.add(obj)

    async def commit(self):
        self._session.commit()

    async def flush(self):
        self._session.flush()

    async def refresh(self, obj):
        self._session.refresh(obj)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture()
def service_db():
    """Set up in-memory DB and patch the session factory for the service."""
    engine = _make_sync_db()
    session = Session(engine)

    def fake_factory():
        return FakeAsyncSession(session)

    with patch.object(gs_service, "get_session_factory", return_value=fake_factory):
        yield session

    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


# ── Tests ──────────────────────────────────────────────────────────────


class TestGetOrCreate:
    """Tests for get_or_create."""

    @pytest.mark.asyncio
    async def test_creates_new_row(self, service_db: Session) -> None:
        result = await gs_service.get_or_create("111111111111111111")
        assert result.discord_guild_id == "111111111111111111"
        assert result.timezone == "UTC"

    @pytest.mark.asyncio
    async def test_returns_existing_row(self, service_db: Session) -> None:
        gs = GuildSettings(discord_guild_id="111111111111111111", timezone="US/Eastern")
        service_db.add(gs)
        service_db.commit()

        result = await gs_service.get_or_create("111111111111111111")
        assert result.timezone == "US/Eastern"


class TestGetSettings:
    """Tests for get_settings."""

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_guild(self, service_db: Session) -> None:
        result = await gs_service.get_settings("999999999999999999")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_existing_settings(self, service_db: Session) -> None:
        gs = GuildSettings(discord_guild_id="111111111111111111")
        service_db.add(gs)
        service_db.commit()

        result = await gs_service.get_settings("111111111111111111")
        assert result is not None
        assert result.discord_guild_id == "111111111111111111"


class TestUpdateChannel:
    """Tests for update_channel."""

    @pytest.mark.asyncio
    async def test_update_onboarding_channel(self, service_db: Session) -> None:
        result = await gs_service.update_channel(
            "111111111111111111", "onboarding_channel_id", "222222222222222222"
        )
        assert result.onboarding_channel_id == "222222222222222222"

    @pytest.mark.asyncio
    async def test_update_announcement_channel(self, service_db: Session) -> None:
        result = await gs_service.update_channel(
            "111111111111111111", "announcement_channel_id", "333333333333333333"
        )
        assert result.announcement_channel_id == "333333333333333333"

    @pytest.mark.asyncio
    async def test_update_contest_alert_channel(self, service_db: Session) -> None:
        result = await gs_service.update_channel(
            "111111111111111111", "contest_alert_channel_id", "444444444444444444"
        )
        assert result.contest_alert_channel_id == "444444444444444444"

    @pytest.mark.asyncio
    async def test_invalid_field_raises(self, service_db: Session) -> None:
        with pytest.raises(ValueError, match="Invalid channel field"):
            await gs_service.update_channel(
                "111111111111111111", "invalid_field", "222222222222222222"
            )


class TestUpdateAlertRole:
    """Tests for update_alert_role."""

    @pytest.mark.asyncio
    async def test_sets_alert_role(self, service_db: Session) -> None:
        result = await gs_service.update_alert_role("111111111111111111", "555555555555555555")
        assert result.alert_role_id == "555555555555555555"


class TestResetSettings:
    """Tests for reset_settings."""

    @pytest.mark.asyncio
    async def test_reset_clears_channels_and_role(self, service_db: Session) -> None:
        # Set up a fully configured guild
        await gs_service.update_channel(
            "111111111111111111", "onboarding_channel_id", "222222222222222222"
        )
        await gs_service.update_channel(
            "111111111111111111", "announcement_channel_id", "333333333333333333"
        )
        await gs_service.update_channel(
            "111111111111111111", "contest_alert_channel_id", "444444444444444444"
        )
        await gs_service.update_alert_role("111111111111111111", "555555555555555555")

        result = await gs_service.reset_settings("111111111111111111")

        assert result is not None
        assert result.onboarding_channel_id is None
        assert result.announcement_channel_id is None
        assert result.contest_alert_channel_id is None
        assert result.alert_role_id is None

    @pytest.mark.asyncio
    async def test_reset_preserves_timezone(self, service_db: Session) -> None:
        gs = GuildSettings(discord_guild_id="111111111111111111", timezone="Asia/Kolkata")
        service_db.add(gs)
        service_db.commit()

        result = await gs_service.reset_settings("111111111111111111")
        assert result is not None
        assert result.timezone == "Asia/Kolkata"

    @pytest.mark.asyncio
    async def test_reset_unknown_guild_returns_none(self, service_db: Session) -> None:
        result = await gs_service.reset_settings("999999999999999999")
        assert result is None
