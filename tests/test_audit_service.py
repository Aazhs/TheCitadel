"""Tests for the audit service."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.db.models import AuditLog
from src.services import audit as audit_service


class FakeAsyncSession:
    """A fake AsyncSession for testing."""

    def __init__(self, execute_result=None):
        self.added = []
        self._execute_result = execute_result

    async def execute(self, stmt):
        if callable(self._execute_result):
            return self._execute_result(stmt)
        return self._execute_result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
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
    with patch("src.services.audit.get_session_factory") as mock:
        yield mock


@pytest.mark.asyncio
async def test_log_action_creates_entry(mock_session_factory) -> None:
    fake_session = FakeAsyncSession()
    mock_session_factory.return_value.return_value = fake_session

    await audit_service.log_action(
        guild_settings_id=1,
        action="test_action",
        performed_by="222",
        target_type="event",
        target_id=333,
        details="some details",
    )

    assert len(fake_session.added) == 1
    log_entry = fake_session.added[0]
    assert isinstance(log_entry, AuditLog)
    assert log_entry.guild_settings_id == 1
    assert log_entry.performed_by_discord_user_id == "222"
    assert log_entry.action == "test_action"
    assert log_entry.target_type == "event"
    assert log_entry.target_id == 333
    assert log_entry.details == "some details"


@pytest.mark.asyncio
async def test_log_action_optional_fields_none(mock_session_factory) -> None:
    fake_session = FakeAsyncSession()
    mock_session_factory.return_value.return_value = fake_session

    await audit_service.log_action(
        guild_settings_id=1,
        action="test_action",
        performed_by="222",
    )

    assert len(fake_session.added) == 1
    log_entry = fake_session.added[0]
    assert log_entry.target_type is None
    assert log_entry.target_id is None
    assert log_entry.details is None
