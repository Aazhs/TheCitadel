from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.db.models import Contest
from src.providers.codeforces import CodeforcesContest
from src.services.contests import get_upcoming_contests, sync_codeforces_contests


class FakeAsyncSession:
    def __init__(self, execute_result=None):
        self.added = []
        self._execute_result = execute_result

    async def execute(self, stmt):
        return self._execute_result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture
def mock_session_factory():
    with patch("src.services.contests.get_session_factory") as mock:
        yield mock


@pytest.fixture
def sample_contests():
    now = int(datetime.now(UTC).timestamp())
    return [
        CodeforcesContest(
            id=1,
            name="Codeforces Round 999 (Div. 1)",
            type="CF",
            phase="BEFORE",
            frozen=False,
            duration_seconds=7200,
            start_time_seconds=now + 86400,
        ),
        CodeforcesContest(
            id=2,
            name="Codeforces Round 1000 (Div. 2)",
            type="CF",
            phase="FINISHED",
            frozen=False,
            duration_seconds=7200,
            start_time_seconds=now - 86400 * 10,  # 10 days ago
        ),
    ]


@pytest.mark.asyncio
async def test_sync_codeforces_contests(sample_contests, mock_session_factory):
    class MockResult:
        def scalars(self):
            return self

        def all(self):
            return []  # No existing contests

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    added, updated = await sync_codeforces_contests(sample_contests)

    assert added == 1  # Only 1 should be added, the other is filtered
    assert updated == 0
    assert len(fake_session.added) == 1
    assert fake_session.added[0].external_contest_id == "1"


@pytest.mark.asyncio
async def test_sync_codeforces_contests_update(sample_contests, mock_session_factory):
    now = datetime.now(UTC)
    existing = Contest(
        platform="codeforces",
        external_contest_id="1",
        name="Old Name",
        url="http",
        start_time_utc=now,
        duration_seconds=7200,
        phase="BEFORE",
    )

    class MockResult:
        def scalars(self):
            return self

        def all(self):
            return [existing]

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    added, updated = await sync_codeforces_contests(sample_contests)

    assert added == 0
    assert updated == 1
    assert len(fake_session.added) == 0
    assert existing.name == "Codeforces Round 999 (Div. 1)"


@pytest.mark.asyncio
async def test_get_upcoming_contests(mock_session_factory):
    now = datetime.now(UTC)
    c1 = Contest(
        platform="codeforces",
        external_contest_id="101",
        name="C1",
        url="http",
        start_time_utc=now + timedelta(days=2),
        duration_seconds=7200,
        phase="BEFORE",
    )

    class MockResult:
        def scalars(self):
            return self

        def all(self):
            return [c1]

    fake_session = FakeAsyncSession(execute_result=MockResult())
    mock_session_factory.return_value.return_value = fake_session

    upcoming = await get_upcoming_contests()
    assert len(upcoming) == 1
    assert upcoming[0].external_contest_id == "101"
