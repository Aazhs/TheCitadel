"""Tests for the lifecycle service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.db.models import Event
from src.services import lifecycle as lifecycle_service


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
    with patch("src.services.lifecycle.get_session_factory") as mock:
        yield mock


@pytest.mark.asyncio
async def test_activate_event_success(mock_session_factory) -> None:
    event = Event(id=1, status="published")

    class MockResult:
        def scalar_one_or_none(self):
            return event

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    res = await lifecycle_service.activate_event(1)
    assert res.status == "active"


@pytest.mark.asyncio
async def test_activate_event_not_found(mock_session_factory) -> None:
    class MockResult:
        def scalar_one_or_none(self):
            return None

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    with pytest.raises(ValueError, match="not found"):
        await lifecycle_service.activate_event(1)


@pytest.mark.asyncio
async def test_end_event_sets_submission_open(mock_session_factory) -> None:
    now = datetime.now(UTC)
    event = Event(id=1, status="active", submission_deadline_utc=None, end_time_utc=now)

    class MockResult:
        def scalar_one_or_none(self):
            return event

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    res = await lifecycle_service.end_event(1, submission_deadline_hours=24)
    assert res.status == "submission_open"
    assert res.submission_deadline_utc is not None


@pytest.mark.asyncio
async def test_end_event_preserves_existing_deadline(mock_session_factory) -> None:
    existing_deadline = datetime.now(UTC) + timedelta(hours=48)
    event = Event(id=1, status="active", submission_deadline_utc=existing_deadline)

    class MockResult:
        def scalar_one_or_none(self):
            return event

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    res = await lifecycle_service.end_event(1, submission_deadline_hours=24)
    assert res.status == "submission_open"
    assert res.submission_deadline_utc == existing_deadline


@pytest.mark.asyncio
async def test_finalize_event_success(mock_session_factory) -> None:
    event = Event(id=1, status="submission_open")

    class MockResult:
        def scalar_one_or_none(self):
            return event

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    res = await lifecycle_service.finalize_event(1)
    assert res.status == "finalized"


@pytest.mark.asyncio
async def test_finalize_event_not_found(mock_session_factory) -> None:
    class MockResult:
        def scalar_one_or_none(self):
            return None

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    with pytest.raises(ValueError, match="not found"):
        await lifecycle_service.finalize_event(1)


@pytest.mark.asyncio
async def test_get_events_to_activate(mock_session_factory) -> None:
    mock_events = [Event(id=1), Event(id=2)]

    class MockResult:
        def scalars(self):
            return self

        def all(self):
            return mock_events

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    now = datetime.now(UTC)
    events = await lifecycle_service.get_events_to_activate(now)
    assert events == mock_events


@pytest.mark.asyncio
async def test_get_events_to_end(mock_session_factory) -> None:
    mock_events = [Event(id=1)]

    class MockResult:
        def scalars(self):
            return self

        def all(self):
            return mock_events

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    now = datetime.now(UTC)
    events = await lifecycle_service.get_events_to_end(now)
    assert events == mock_events


@pytest.mark.asyncio
async def test_get_events_to_finalize(mock_session_factory) -> None:
    mock_events = [Event(id=1)]

    class MockResult:
        def scalars(self):
            return self

        def all(self):
            return mock_events

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    now = datetime.now(UTC)
    events = await lifecycle_service.get_events_to_finalize(now)
    assert events == mock_events
