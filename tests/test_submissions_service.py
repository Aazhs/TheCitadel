"""Tests for the submissions service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.db.models import Event, EventSubmission, GuildMember, User
from src.services import submissions as submissions_service


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
    with patch("src.services.submissions.get_session_factory") as mock:
        yield mock


@pytest.mark.asyncio
async def test_create_submission_pending_when_approval_required(mock_session_factory) -> None:
    now = datetime.now(UTC)
    event = Event(
        id=1,
        status="submission_open",
        submission_deadline_utc=now + timedelta(hours=1),
        results_require_moderator_approval=True,
    )
    user = User(id=1, discord_user_id="222")
    member = GuildMember(id=1, guild_settings_id=1, user_id=1)

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
                return None

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    sub = await submissions_service.create_or_update_submission(
        1,
        "111",
        "222",
        5,
        claimed_rank=1,
        claimed_rating_before=None,
        claimed_rating_after=None,
        evidence_url="http://test.com",
        reflection="test",
    )

    assert sub.verification_status == "pending"
    assert len(fake_session.added) > 0


@pytest.mark.asyncio
async def test_create_submission_verified_when_no_approval(mock_session_factory) -> None:
    now = datetime.now(UTC)
    event = Event(
        id=1,
        status="submission_open",
        submission_deadline_utc=now + timedelta(hours=1),
        results_require_moderator_approval=False,
    )

    class MockResult:
        def __init__(self):
            self.calls = 0

        def scalar_one_or_none(self):
            self.calls += 1
            if self.calls == 1:
                return event
            elif self.calls == 2 or self.calls == 3 or self.calls == 4:
                return None

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    sub = await submissions_service.create_or_update_submission(
        1,
        "111",
        "222",
        5,
        claimed_rank=1,
        claimed_rating_before=None,
        claimed_rating_after=None,
        evidence_url="http://test.com",
        reflection="test",
    )

    assert sub.verification_status == "verified"


@pytest.mark.asyncio
async def test_create_submission_calculates_rating_change(mock_session_factory) -> None:
    now = datetime.now(UTC)
    event = Event(
        id=1,
        status="submission_open",
        submission_deadline_utc=now + timedelta(hours=1),
        results_require_moderator_approval=False,
    )

    class MockResult:
        def __init__(self):
            self.calls = 0

        def scalar_one_or_none(self):
            self.calls += 1
            if self.calls == 1:
                return event
            return None

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    sub = await submissions_service.create_or_update_submission(
        1,
        "111",
        "222",
        5,
        claimed_rank=1,
        claimed_rating_before=1500,
        claimed_rating_after=1600,
        evidence_url="http://test.com",
        reflection="test",
    )

    assert sub.claimed_rating_change == 100


@pytest.mark.asyncio
async def test_create_submission_rejects_wrong_status(mock_session_factory) -> None:
    event = Event(
        id=1, status="active", submission_deadline_utc=datetime.now(UTC) + timedelta(hours=1)
    )

    class MockResult:
        def scalar_one_or_none(self):
            return event

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    with pytest.raises(ValueError, match="submission_open"):
        await submissions_service.create_or_update_submission(
            1,
            "111",
            "222",
            5,
            claimed_rank=1,
            claimed_rating_before=None,
            claimed_rating_after=None,
            evidence_url="http://test.com",
            reflection="test",
        )


@pytest.mark.asyncio
async def test_create_submission_rejects_past_deadline(mock_session_factory) -> None:
    event = Event(
        id=1,
        status="submission_open",
        submission_deadline_utc=datetime.now(UTC) - timedelta(hours=1),
    )

    class MockResult:
        def scalar_one_or_none(self):
            return event

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    with pytest.raises(ValueError, match="Submission deadline has passed"):
        await submissions_service.create_or_update_submission(
            1,
            "111",
            "222",
            5,
            claimed_rank=1,
            claimed_rating_before=None,
            claimed_rating_after=None,
            evidence_url="http://test.com",
            reflection="test",
        )


@pytest.mark.asyncio
async def test_update_existing_submission(mock_session_factory) -> None:
    now = datetime.now(UTC)
    event = Event(
        id=1,
        status="submission_open",
        submission_deadline_utc=now + timedelta(hours=1),
        results_require_moderator_approval=True,
    )
    existing_sub = EventSubmission(
        id=1, event_id=1, questions_solved=1, claimed_rank=1, verification_status="pending"
    )

    class MockResult:
        def __init__(self):
            self.calls = 0

        def scalar_one_or_none(self):
            self.calls += 1
            if self.calls == 1:
                return event
            elif self.calls == 2:
                return User(id=1)
            elif self.calls == 3:
                return GuildMember(id=1)
            elif self.calls == 4:
                return existing_sub

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    sub = await submissions_service.create_or_update_submission(
        1,
        "111",
        "222",
        10,
        claimed_rank=2,
        claimed_rating_before=None,
        claimed_rating_after=None,
        evidence_url="http://test2.com",
        reflection="updated",
    )

    assert sub.questions_solved == 10
    assert sub.claimed_rank == 2


@pytest.mark.asyncio
async def test_approve_submission_success(mock_session_factory) -> None:
    sub = EventSubmission(id=1, verification_status="pending")

    class MockResult:
        def scalar_one_or_none(self):
            return sub

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    res = await submissions_service.approve_submission(1, "admin123", note="Looks good")
    assert res.verification_status == "verified"
    assert res.verified_by_discord_user_id == "admin123"
    assert res.moderator_note == "Looks good"


@pytest.mark.asyncio
async def test_approve_rejects_non_pending(mock_session_factory) -> None:
    sub = EventSubmission(id=1, verification_status="verified")

    class MockResult:
        def scalar_one_or_none(self):
            return sub

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    with pytest.raises(ValueError, match="not pending"):
        await submissions_service.approve_submission(1, "admin123")


@pytest.mark.asyncio
async def test_reject_submission_success(mock_session_factory) -> None:
    sub = EventSubmission(id=1, verification_status="pending")

    class MockResult:
        def scalar_one_or_none(self):
            return sub

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    res = await submissions_service.reject_submission(1, "admin123", "Fake evidence")
    assert res.verification_status == "rejected"
    assert res.verified_by_discord_user_id == "admin123"
    assert res.moderator_note == "Fake evidence"


@pytest.mark.asyncio
async def test_reject_rejects_non_pending(mock_session_factory) -> None:
    sub = EventSubmission(id=1, verification_status="verified")

    class MockResult:
        def scalar_one_or_none(self):
            return sub

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    with pytest.raises(ValueError, match="not pending"):
        await submissions_service.reject_submission(1, "admin123", "Fake evidence")
