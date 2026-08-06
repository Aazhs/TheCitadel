"""Unit tests for database models — uses in-memory SQLite, no live Supabase required."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.base import Base
from src.db.models import GuildMember, GuildSettings, User


@pytest.fixture()
def db_session():
    """Create an in-memory SQLite database and return a session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


class TestGuildSettings:
    """Tests for the GuildSettings model."""

    def test_create_guild_settings(self, db_session: Session) -> None:
        gs = GuildSettings(discord_guild_id="123456789012345678")
        db_session.add(gs)
        db_session.commit()

        result = db_session.execute(select(GuildSettings)).scalar_one()
        assert result.discord_guild_id == "123456789012345678"
        assert result.timezone == "UTC"
        assert result.reminders_enabled is True
        assert result.onboarding_channel_id is None
        assert result.announcement_channel_id is None
        assert result.contest_alert_channel_id is None
        assert result.alert_role_id is None

    def test_unique_guild_id(self, db_session: Session) -> None:
        gs1 = GuildSettings(discord_guild_id="111111111111111111")
        gs2 = GuildSettings(discord_guild_id="111111111111111111")
        db_session.add(gs1)
        db_session.commit()
        db_session.add(gs2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_optional_channel_fields(self, db_session: Session) -> None:
        gs = GuildSettings(
            discord_guild_id="222222222222222222",
            onboarding_channel_id="999999999999999999",
            announcement_channel_id="888888888888888888",
            contest_alert_channel_id="777777777777777777",
            alert_role_id="666666666666666666",
        )
        db_session.add(gs)
        db_session.commit()
        result = db_session.execute(select(GuildSettings)).scalar_one()
        assert result.onboarding_channel_id == "999999999999999999"
        assert result.alert_role_id == "666666666666666666"

    def test_custom_timezone(self, db_session: Session) -> None:
        gs = GuildSettings(discord_guild_id="333333333333333333", timezone="Asia/Kolkata")
        db_session.add(gs)
        db_session.commit()
        result = db_session.execute(select(GuildSettings)).scalar_one()
        assert result.timezone == "Asia/Kolkata"

    def test_repr(self) -> None:
        gs = GuildSettings(id=1, discord_guild_id="111")
        assert "GuildSettings" in repr(gs)
        assert "111" in repr(gs)


class TestUser:
    """Tests for the User model."""

    def test_create_user(self, db_session: Session) -> None:
        user = User(discord_user_id="123456789012345678")
        db_session.add(user)
        db_session.commit()
        result = db_session.execute(select(User)).scalar_one()
        assert result.discord_user_id == "123456789012345678"

    def test_unique_user_id(self, db_session: Session) -> None:
        u1 = User(discord_user_id="111111111111111111")
        u2 = User(discord_user_id="111111111111111111")
        db_session.add(u1)
        db_session.commit()
        db_session.add(u2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_repr(self) -> None:
        u = User(id=1, discord_user_id="111")
        assert "User" in repr(u)


class TestGuildMember:
    """Tests for the GuildMember model."""

    def test_create_guild_member(self, db_session: Session) -> None:
        gs = GuildSettings(discord_guild_id="111111111111111111")
        user = User(discord_user_id="222222222222222222")
        db_session.add_all([gs, user])
        db_session.commit()

        member = GuildMember(guild_settings_id=gs.id, user_id=user.id)
        db_session.add(member)
        db_session.commit()

        result = db_session.execute(select(GuildMember)).scalar_one()
        assert result.guild_settings_id == gs.id
        assert result.user_id == user.id
        assert result.verified_competitor is False

    def test_unique_guild_member_constraint(self, db_session: Session) -> None:
        gs = GuildSettings(discord_guild_id="111111111111111111")
        user = User(discord_user_id="222222222222222222")
        db_session.add_all([gs, user])
        db_session.commit()

        m1 = GuildMember(guild_settings_id=gs.id, user_id=user.id)
        db_session.add(m1)
        db_session.commit()

        m2 = GuildMember(guild_settings_id=gs.id, user_id=user.id)
        db_session.add(m2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_verified_competitor_default(self, db_session: Session) -> None:
        gs = GuildSettings(discord_guild_id="111111111111111111")
        user = User(discord_user_id="222222222222222222")
        db_session.add_all([gs, user])
        db_session.commit()

        member = GuildMember(guild_settings_id=gs.id, user_id=user.id)
        db_session.add(member)
        db_session.commit()
        assert member.verified_competitor is False

    def test_set_verified_competitor(self, db_session: Session) -> None:
        gs = GuildSettings(discord_guild_id="111111111111111111")
        user = User(discord_user_id="222222222222222222")
        db_session.add_all([gs, user])
        db_session.commit()

        member = GuildMember(guild_settings_id=gs.id, user_id=user.id, verified_competitor=True)
        db_session.add(member)
        db_session.commit()
        assert member.verified_competitor is True

    def test_relationships(self, db_session: Session) -> None:
        gs = GuildSettings(discord_guild_id="111111111111111111")
        user = User(discord_user_id="222222222222222222")
        db_session.add_all([gs, user])
        db_session.commit()

        member = GuildMember(guild_settings_id=gs.id, user_id=user.id)
        db_session.add(member)
        db_session.commit()

        # Refresh to load relationships
        db_session.refresh(gs)
        db_session.refresh(user)
        assert len(gs.members) == 1
        assert len(user.memberships) == 1
        assert gs.members[0].user_id == user.id

    def test_repr(self) -> None:
        m = GuildMember(id=1, guild_settings_id=2, user_id=3)
        assert "GuildMember" in repr(m)
