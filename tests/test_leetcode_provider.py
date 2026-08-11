import pytest
import respx
import httpx
from src.providers.leetcode import fetch_contests, fetch_user_stats

@pytest.mark.asyncio
@respx.mock
async def test_fetch_user_stats():
    mock_data = {
        "data": {
            "matchedUser": {
                "submitStats": {
                    "acSubmissionNum": [
                        {"difficulty": "Easy", "count": 10},
                        {"difficulty": "Medium", "count": 5},
                        {"difficulty": "Hard", "count": 2},
                    ]
                }
            },
            "userContestRanking": {
                "rating": 1500.5,
                "globalRanking": 50000
            }
        }
    }
    
    respx.post("https://leetcode.com/graphql").mock(
        return_value=httpx.Response(200, json=mock_data)
    )
    
    user = await fetch_user_stats("testuser")
    assert user is not None
    assert user.handle == "testuser"
    assert user.rating == 1500
    assert user.easy_solved == 10
    assert user.medium_solved == 5
    assert user.hard_solved == 2
    assert user.global_rank == 50000

@pytest.mark.asyncio
@respx.mock
async def test_fetch_contests():
    mock_data = {
        "data": {
            "allContests": [
                {
                    "titleSlug": "weekly-contest-400",
                    "title": "Weekly Contest 400",
                    "startTime": 1700000000,
                    "duration": 5400
                }
            ]
        }
    }
    
    respx.post("https://leetcode.com/graphql").mock(
        return_value=httpx.Response(200, json=mock_data)
    )
    
    contests = await fetch_contests()
    assert contests is not None
    assert len(contests) == 1
    assert contests[0].title_slug == "weekly-contest-400"
    assert contests[0].title == "Weekly Contest 400"
    assert contests[0].start_time_utc == 1700000000
    assert contests[0].duration_seconds == 5400
