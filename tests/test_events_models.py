"""Unit tests for event models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.db.base import Base
from src.db.models import Event, EventRegistration, GuildMember, GuildSettings, User


@pytest.fixture()
def db_session():
    """Create an in-memory SQLite database and return a session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def setup_data(db_session: Session):
    """Create standard setup objects."""
    gs = GuildSettings(discord_guild_id="111")
    user = User(discord_user_id="222")
    db_session.add_all([gs, user])
    db_session.commit()
    member = GuildMember(guild_settings_id=gs.id, user_id=user.id)
    db_session.add(member)
    db_session.commit()
    return gs, user, member


class TestEventModel:
    def test_create_event(self, db_session: Session, setup_data) -> None:
        gs, _, _ = setup_data
        now = datetime.now(UTC)
        event = Event(
            guild_settings_id=gs.id,
            title="Codeforces Round",
            event_type="codeforces_contest",
            description="Testing",
            start_time_utc=now,
            end_time_utc=now + timedelta(hours=2),
            created_by_discord_user_id="333",
        )
        db_session.add(event)
        db_session.commit()

        result = db_session.execute(select(Event)).scalar_one()
        assert result.title == "Codeforces Round"
        assert result.status == "draft"  # Default
        assert result.platform is None

    def test_event_nullable_fields(self, db_session: Session, setup_data) -> None:
        gs, _, _ = setup_data
        now = datetime.now(UTC)
        event = Event(
            guild_settings_id=gs.id,
            title="All fields event",
            event_type="custom_practice",
            description="Testing nullables",
            start_time_utc=now,
            end_time_utc=now + timedelta(hours=2),
            created_by_discord_user_id="333",
            platform="custom",
            official_url="http://example.com",
            registration_deadline_utc=now - timedelta(hours=1),
            announcement_channel_id="c1",
            discussion_channel_id="c2",
            results_channel_id="c3",
        )
        db_session.add(event)
        db_session.commit()

        result = db_session.execute(select(Event)).scalar_one()
        assert result.platform == "custom"
        assert result.official_url == "http://example.com"
        assert result.registration_deadline_utc is not None
        assert result.announcement_channel_id == "c1"
        assert result.discussion_channel_id == "c2"
        assert result.results_channel_id == "c3"

    def test_cascade_delete(self, db_session: Session, setup_data) -> None:
        gs, _, _ = setup_data
        now = datetime.now(UTC)
        event = Event(
            guild_settings_id=gs.id,
            title="To Delete",
            event_type="codeforces_contest",
            description="Testing cascade",
            start_time_utc=now,
            end_time_utc=now + timedelta(hours=2),
            created_by_discord_user_id="333",
        )
        db_session.add(event)
        db_session.commit()

        # Delete guild settings
        db_session.delete(gs)
        db_session.commit()

        # Event should be deleted
        assert db_session.execute(select(Event)).scalar_one_or_none() is None

    def test_status_field(self, db_session: Session, setup_data) -> None:
        gs, _, _ = setup_data
        now = datetime.now(UTC)
        for status in (
            "draft",
            "published",
            "registration_open",
            "active",
            "ended",
            "submission_open",
            "finalized",
            "cancelled",
        ):
            event = Event(
                guild_settings_id=gs.id,
                title=f"Event {status}",
                event_type="codeforces_contest",
                description="Testing status",
                start_time_utc=now,
                end_time_utc=now + timedelta(hours=2),
                created_by_discord_user_id="333",
                status=status,
            )
            db_session.add(event)
        db_session.commit()

        results = db_session.execute(select(Event)).scalars().all()
        assert len(results) == 8
        statuses = {e.status for e in results}
        assert statuses == {
            "draft",
            "published",
            "registration_open",
            "active",
            "ended",
            "submission_open",
            "finalized",
            "cancelled",
        }

    def test_repr(self, db_session: Session, setup_data) -> None:
        gs, _, _ = setup_data
        now = datetime.now(UTC)
        event = Event(
            id=10,
            guild_settings_id=gs.id,
            title="Repr Event",
            event_type="codeforces_contest",
            description="Testing repr",
            start_time_utc=now,
            end_time_utc=now + timedelta(hours=2),
            created_by_discord_user_id="333",
            status="active",
        )
        r = repr(event)
        assert "Event" in r
        assert "10" in r
        assert "Repr Event" in r
        assert "active" in r


class TestEventRegistrationModel:
    def test_create_registration(self, db_session: Session, setup_data) -> None:
        gs, _, member = setup_data
        now = datetime.now(UTC)
        event = Event(
            guild_settings_id=gs.id,
            title="Codeforces Round",
            event_type="codeforces_contest",
            description="Testing",
            start_time_utc=now,
            end_time_utc=now + timedelta(hours=2),
            created_by_discord_user_id="333",
        )
        db_session.add(event)
        db_session.commit()

        reg = EventRegistration(event_id=event.id, guild_member_id=member.id)
        db_session.add(reg)
        db_session.commit()

        result = db_session.execute(select(EventRegistration)).scalar_one()
        assert result.event_id == event.id
        assert result.guild_member_id == member.id
        assert result.status == "registered"

    def test_unique_constraint(self, db_session: Session, setup_data) -> None:
        gs, _, member = setup_data
        now = datetime.now(UTC)
        event = Event(
            guild_settings_id=gs.id,
            title="Codeforces Round",
            event_type="codeforces_contest",
            description="Testing",
            start_time_utc=now,
            end_time_utc=now + timedelta(hours=2),
            created_by_discord_user_id="333",
        )
        db_session.add(event)
        db_session.commit()

        reg1 = EventRegistration(event_id=event.id, guild_member_id=member.id)
        db_session.add(reg1)
        db_session.commit()

        reg2 = EventRegistration(event_id=event.id, guild_member_id=member.id)
        db_session.add(reg2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_repr(self, db_session: Session, setup_data) -> None:
        gs, _, member = setup_data
        now = datetime.now(UTC)
        event = Event(
            id=1,
            guild_settings_id=gs.id,
            title="Codeforces Round",
            event_type="codeforces_contest",
            description="Testing",
            start_time_utc=now,
            end_time_utc=now + timedelta(hours=2),
            created_by_discord_user_id="333",
        )
        db_session.add(event)
        db_session.commit()

        reg = EventRegistration(id=100, event_id=event.id, guild_member_id=member.id)
        r = repr(reg)
        assert "EventRegistration" in r
        assert "100" in r
        assert str(event.id) in r
        assert str(member.id) in r
