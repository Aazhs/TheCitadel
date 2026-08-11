"""Tests for the events service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.db.models import Event, EventRegistration, GuildMember, User
from src.services import events as event_service


class FakeAsyncSession:
    """A fake AsyncSession for testing."""

    def __init__(self, execute_result=None):
        self.added = []
        self.deleted = []
        self._execute_result = execute_result

    async def execute(self, stmt):
        if callable(self._execute_result):
            return self._execute_result(stmt)
        return self._execute_result

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        for obj in self.added:
            if not getattr(obj, "id", None):
                obj.id = 999

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, obj):
        if not getattr(obj, "id", None):
            obj.id = 999

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def mock_session_factory():
    """Returns a patcher for get_session_factory."""
    with patch("src.services.events.get_session_factory") as mock:
        yield mock


@pytest.mark.asyncio
async def test_create_event_draft(mock_session_factory) -> None:
    class MockResult:
        def scalar_one_or_none(self):
            return None

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    now = datetime.now(UTC)
    end = now + timedelta(hours=2)

    event = await event_service.create_event(
        "111", "Test Event", "codeforces_contest", "Desc", now, end, "222"
    )

    assert len(fake_session.added) == 2  # GuildSettings + Event
    assert event.title == "Test Event"
    assert event.status == "draft"


@pytest.mark.asyncio
async def test_publish_event_success(mock_session_factory) -> None:
    event = Event(id=1, status="draft")

    class MockResult:
        def scalar_one_or_none(self):
            return event

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    res = await event_service.publish_event(1, "111")
    assert res.status == "published"
    assert res is event


@pytest.mark.asyncio
async def test_publish_event_rejects_non_draft(mock_session_factory) -> None:
    event = Event(id=1, status="published")

    class MockResult:
        def scalar_one_or_none(self):
            return event

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    with pytest.raises(ValueError, match="Cannot publish event"):
        await event_service.publish_event(1, "111")


@pytest.mark.asyncio
async def test_cancel_event_success(mock_session_factory) -> None:
    event = Event(id=1, status="published")

    class MockResult:
        def scalar_one_or_none(self):
            return event

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    res = await event_service.cancel_event(1, "111")
    assert res.status == "cancelled"


@pytest.mark.asyncio
async def test_cancel_event_rejects_already_cancelled(mock_session_factory) -> None:
    event = Event(id=1, status="cancelled")

    class MockResult:
        def scalar_one_or_none(self):
            return event

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    with pytest.raises(ValueError, match="Cannot cancel event"):
        await event_service.cancel_event(1, "111")


@pytest.mark.asyncio
async def test_register_for_event_happy_path(mock_session_factory) -> None:
    event = Event(
        id=1,
        status="published",
        guild_settings_id=1,
        registration_deadline_utc=datetime.now(UTC) + timedelta(hours=1),
    )

    class MockResult:
        def __init__(self):
            self.calls = 0

        def scalar_one_or_none(self):
            self.calls += 1
            if self.calls == 1:
                return event
            return None  # Returns None for User, GuildMember, and EventRegistration

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    reg = await event_service.register_for_event(1, "111", "222")
    assert reg.status == "registered"
    assert reg.event_id == 1
    # User, GuildMember, EventRegistration should be added
    assert len(fake_session.added) == 3


@pytest.mark.asyncio
async def test_register_for_event_rejected_after_deadline(mock_session_factory) -> None:
    event = Event(
        id=1,
        status="published",
        guild_settings_id=1,
        registration_deadline_utc=datetime.now(UTC) - timedelta(hours=1),
    )

    class MockResult:
        def scalar_one_or_none(self):
            return event

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    with pytest.raises(ValueError, match="Registration deadline has passed"):
        await event_service.register_for_event(1, "111", "222")


@pytest.mark.asyncio
async def test_register_for_event_rejected_cancelled(mock_session_factory) -> None:
    event = Event(id=1, status="cancelled", guild_settings_id=1)

    class MockResult:
        def scalar_one_or_none(self):
            return event

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    with pytest.raises(ValueError, match="Registration is not open"):
        await event_service.register_for_event(1, "111", "222")


@pytest.mark.asyncio
async def test_register_for_event_duplicate(mock_session_factory) -> None:
    event = Event(id=1, status="published", guild_settings_id=1)
    user = User(id=1, discord_user_id="222")
    member = GuildMember(id=1, guild_settings_id=1, user_id=1)
    existing_reg = EventRegistration(id=1, event_id=1, guild_member_id=1)

    class MockResult:
        def __init__(self):
            self.calls = 0

        def scalar_one_or_none(self):
            self.calls += 1
            if self.calls == 1:
                return event
            elif self.calls == 2:
                return user
            elif self.calls == 3:
                return member
            elif self.calls == 4:
                return existing_reg

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    with pytest.raises(ValueError, match="You are already registered"):
        await event_service.register_for_event(1, "111", "222")


@pytest.mark.asyncio
async def test_get_user_events(mock_session_factory) -> None:
    events = [Event(id=1), Event(id=2)]

    class MockResult:
        def scalars(self):
            return self

        def all(self):
            return events

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    res = await event_service.get_user_events("111", "222")
    assert res == events


@pytest.mark.asyncio
async def test_list_events(mock_session_factory) -> None:
    events = [Event(id=1)]

    class MockResult:
        def scalars(self):
            return self

        def all(self):
            return events

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    res = await event_service.list_events("111")
    assert res == events


@pytest.mark.asyncio
async def test_get_registration_count(mock_session_factory) -> None:
    class MockResult:
        def scalar_one(self):
            return 5

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    count = await event_service.get_registration_count(1)
    assert count == 5
