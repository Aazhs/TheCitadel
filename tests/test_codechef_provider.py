import pytest
import respx
import httpx
from datetime import datetime, UTC
from src.providers.codechef import fetch_contests, fetch_user, CodeChefContest

@pytest.mark.asyncio
@respx.mock
async def test_fetch_user():
    html = '''
    <div class="rating-number">1500</div>
    (Highest Rating 1600)
    '''
    respx.get("https://www.codechef.com/users/testuser").mock(
        return_value=httpx.Response(200, text=html)
    )
    user = await fetch_user("testuser")
    assert user is not None
    assert user.handle == "testuser"
    assert user.rating == 1500
    assert user.max_rating == 1600
    assert user.stars == 2

@pytest.mark.asyncio
@respx.mock
async def test_fetch_contests():
    mock_data = {
        "future_contests": [
            {
                "contest_code": "START123",
                "contest_name": "Starters 123",
                "contest_start_date": "08 Aug 2026 14:30:00",
                "contest_end_date": "08 Aug 2026 17:30:00",
                "contest_duration": "180"
            }
        ],
        "present_contests": []
    }
    
    respx.get("https://www.codechef.com/api/list/contests/all").mock(
        return_value=httpx.Response(200, json=mock_data)
    )
    
    contests = await fetch_contests()
    assert contests is not None
    assert len(contests) == 1
    assert contests[0].code == "START123"
    assert contests[0].name == "Starters 123"
    assert contests[0].duration_minutes == 180
