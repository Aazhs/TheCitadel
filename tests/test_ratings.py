import pytest
from src.db.models import LinkedAccount
from src.services.ratings import calculate_cp_rating, calculate_dsa_rating, _get_star_tier
from src.providers.leetcode import LeetCodeUserStats
import unittest.mock as mock

def test_calculate_cp_rating():
    # Only CodeChef
    acc1 = LinkedAccount(platform="codechef", handle="test1", current_rating=1500)
    assert calculate_cp_rating([acc1]) == 1500

    # Only Codeforces
    acc2 = LinkedAccount(platform="codeforces", handle="test2", current_rating=1500)
    assert calculate_cp_rating([acc2]) == 1600  # +100

    # Only LeetCode
    acc3 = LinkedAccount(platform="leetcode", handle="test3", current_rating=1800)
    assert calculate_cp_rating([acc3]) == 1500  # -300

    # Multiple platforms (gets +50 bonus)
    # 1500 (CC), 1400 (CF) -> 1400+100=1500. Max=1500. +50 bonus = 1550
    acc4 = LinkedAccount(platform="codeforces", handle="test4", current_rating=1400)
    assert calculate_cp_rating([acc1, acc4]) == 1550

    # Test ignoring unrated
    acc5 = LinkedAccount(platform="codechef", handle="unrated", current_rating=None)
    assert calculate_cp_rating([acc5, acc3]) == 1500 # Max LC(1500), no bonus since only 1 valid rating


@pytest.mark.asyncio
@mock.patch("src.services.ratings.fetch_user_stats")
async def test_calculate_dsa_rating(mock_fetch):
    # Only CodeChef
    acc1 = LinkedAccount(platform="codechef", handle="test1", current_rating=1500)
    assert await calculate_dsa_rating([acc1]) == 1800 # +300

    # Only Codeforces
    acc2 = LinkedAccount(platform="codeforces", handle="test2", current_rating=1500)
    assert await calculate_dsa_rating([acc2]) == 1900 # +400

    # Only LeetCode
    acc3 = LinkedAccount(platform="leetcode", handle="test3", current_rating=1800)
    assert await calculate_dsa_rating([acc3]) == 1800 # +0

    # Multiple platforms, no bonus for DSA
    assert await calculate_dsa_rating([acc1, acc2, acc3]) == 1900

    # Test unrated LeetCode fallback
    acc_unrated = LinkedAccount(platform="leetcode", handle="unrated", current_rating=None)
    
    mock_fetch.return_value = LeetCodeUserStats(
        handle="unrated",
        rating=None,
        easy_solved=50,   # * 1
        medium_solved=10, # * 3
        hard_solved=2     # * 5
    )
    # Expected: 1000 + 50 + 30 + 10 = 1090
    assert await calculate_dsa_rating([acc_unrated]) == 1090

def test_get_star_tier():
    # CP
    assert _get_star_tier(1300, False) == 1
    assert _get_star_tier(1400, False) == 2
    assert _get_star_tier(1599, False) == 2
    assert _get_star_tier(1600, False) == 3
    assert _get_star_tier(1899, False) == 3
    assert _get_star_tier(1900, False) == 4
    assert _get_star_tier(2099, False) == 4
    assert _get_star_tier(2100, False) == 5

    # DSA
    assert _get_star_tier(1300, True) == 1
    assert _get_star_tier(1400, True) == 2
    assert _get_star_tier(1599, True) == 2
    assert _get_star_tier(1600, True) == 3
    assert _get_star_tier(1799, True) == 3
    assert _get_star_tier(1800, True) == 4
    assert _get_star_tier(2099, True) == 4
    assert _get_star_tier(2100, True) == 5
