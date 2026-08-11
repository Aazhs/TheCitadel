"""Tests for the linked accounts service."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.db.models import GuildMember, GuildSettings, LinkedAccount, User
from src.providers.codeforces import CodeforcesUser
from src.services import linked_accounts as la_service


class FakeAsyncSession:
    """A fake AsyncSession for testing."""

    def __init__(self, execute_result=None):
        self.added = []
        self.deleted = []
        self._execute_result = execute_result

    async def execute(self, stmt):
        return self._execute_result

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        pass

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
    with patch("src.services.linked_accounts.get_session_factory") as mock:
        yield mock


@pytest.mark.asyncio
async def test_link_account_new(mock_session_factory) -> None:
    """Test linking a new account creates all necessary rows."""

    # We will mock the database queries so they return None for existing rows
    class MockResult:
        def scalar_one_or_none(self):
            return None

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    cf_user = CodeforcesUser(
        handle="tourist",
        rating=3900,
        max_rating=4000,
        rank="legendary grandmaster",
        max_rank="legendary grandmaster",
        title_photo=None,
        avatar=None,
    )
    res = await la_service.link_account(
        "111", 
        "222", 
        "codeforces", 
        "tourist", 
        profile_url="https://codeforces.com/profile/tourist",
        validation_status="validated",
        current_rating=3900,
        max_rating=4000
    )

    assert res.platform == "codeforces"
    assert res.handle == "tourist"
    assert res.normalized_handle == "tourist"
    assert res.current_rating == 3900
    
    # 4 added things: gs, user, member, account
    assert len(fake_session.added) == 4
    assert any(isinstance(obj, GuildSettings) for obj in fake_session.added)
    assert any(isinstance(obj, User) for obj in fake_session.added)
    assert any(isinstance(obj, GuildMember) for obj in fake_session.added)


@pytest.mark.asyncio
async def test_link_account_existing(mock_session_factory) -> None:
    """Test linking an account updates the existing one."""

    gs = GuildSettings(id=1, discord_guild_id="111")
    user = User(id=1, discord_user_id="222")
    member = GuildMember(id=1, guild_settings_id=1, user_id=1, verified_competitor=False)
    account = LinkedAccount(
        id=1, guild_member_id=1, platform="codeforces", handle="old", normalized_handle="old"
    )

    class MockResult:
        def __init__(self):
            self.calls = 0

        def scalar_one_or_none(self):
            self.calls += 1
            if self.calls == 1:
                return gs
            elif self.calls == 2:
                return user
            elif self.calls == 3:
                return member
            else:
                return account

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    res = await la_service.link_account(
        "111", 
        "222", 
        "codeforces", 
        "New_Handle", 
        profile_url="https://codeforces.com/profile/new_handle",
        validation_status="validated",
        current_rating=2000,
        max_rating=2100
    )

    # Nothing new should be added
    assert len(fake_session.added) == 0
    # The account should be updated
    assert account.handle == "New_Handle"
    assert account.normalized_handle == "new_handle"
    assert account.current_rating == 2000
    assert res is account
    assert member.verified_competitor is True


@pytest.mark.asyncio
async def test_unlink_account_success(mock_session_factory) -> None:
    """Test unlinking removes the account and updates verified_competitor if needed."""

    member = GuildMember(id=1)
    account = LinkedAccount(id=1)

    class MockResult:
        def __init__(self):
            self.calls = 0

        def scalar_one_or_none(self):
            self.calls += 1
            if self.calls == 1:
                return member
            elif self.calls == 2:
                return account

        def scalars(self):
            return self

        def all(self):
            return []  # No remaining accounts

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    success = await la_service.unlink_account("111", "222", "codeforces")

    assert success is True
    assert len(fake_session.deleted) == 1
    assert fake_session.deleted[0] is account
    assert member.verified_competitor is False


@pytest.mark.asyncio
async def test_unlink_account_not_found(mock_session_factory) -> None:
    """Test unlinking when no account exists."""

    class MockResult:
        def scalar_one_or_none(self):
            return None  # No member or account found

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    success = await la_service.unlink_account("111", "222", "codeforces")

    assert success is False
    assert len(fake_session.deleted) == 0
