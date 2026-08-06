"""Tests for the Codeforces API provider."""

from __future__ import annotations

import httpx
import pytest

from src.providers.codeforces import fetch_contests, fetch_user


@pytest.mark.asyncio
async def test_fetch_user_success(respx_mock) -> None:
    """Test fetching a valid user."""
    respx_mock.get("https://codeforces.com/api/user.info?handles=tourist").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "OK",
                "result": [
                    {
                        "handle": "tourist",
                        "rating": 3900,
                        "maxRating": 4000,
                        "rank": "legendary grandmaster",
                        "maxRank": "legendary grandmaster",
                        "titlePhoto": "http://photo.jpg",
                        "avatar": "http://avatar.jpg",
                    }
                ],
            },
        )
    )

    user = await fetch_user("tourist")
    assert user is not None
    assert user.handle == "tourist"
    assert user.rating == 3900
    assert user.max_rating == 4000
    assert user.rank == "legendary grandmaster"


@pytest.mark.asyncio
async def test_fetch_user_not_found(respx_mock) -> None:
    """Test fetching an invalid user handle."""
    respx_mock.get("https://codeforces.com/api/user.info?handles=invalid_handle").mock(
        return_value=httpx.Response(
            400,
            json={
                "status": "FAILED",
                "comment": "handles: User with handle invalid_handle not found",
            },
        )
    )

    user = await fetch_user("invalid_handle")
    assert user is None


@pytest.mark.asyncio
async def test_fetch_contests_success(respx_mock) -> None:
    """Test fetching contests successfully."""
    respx_mock.get("https://codeforces.com/api/contest.list").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "OK",
                "result": [
                    {
                        "id": 1,
                        "name": "Contest 1",
                        "type": "CF",
                        "phase": "BEFORE",
                        "frozen": False,
                        "durationSeconds": 7200,
                        "startTimeSeconds": 1000000,
                    }
                ],
            },
        )
    )

    contests = await fetch_contests()
    assert contests is not None
    assert len(contests) == 1
    assert contests[0].id == 1
    assert contests[0].name == "Contest 1"


@pytest.mark.asyncio
async def test_fetch_contests_failure(respx_mock) -> None:
    """Test failure when fetching contests."""
    respx_mock.get("https://codeforces.com/api/contest.list").mock(return_value=httpx.Response(500))

    contests = await fetch_contests()
    assert contests is None


@pytest.mark.asyncio
async def test_fetch_user_rate_limit(respx_mock) -> None:
    """Test handling of rate limit responses."""
    respx_mock.get("https://codeforces.com/api/user.info?handles=tourist").mock(
        return_value=httpx.Response(
            200,
            json={"status": "FAILED", "comment": "Call limit exceeded"},
        )
    )

    user = await fetch_user("tourist")
    assert user is None


@pytest.mark.asyncio
async def test_fetch_user_network_error(respx_mock) -> None:
    """Test handling of network timeouts/errors."""
    respx_mock.get("https://codeforces.com/api/user.info?handles=tourist").mock(
        side_effect=httpx.ConnectTimeout("Timeout")
    )

    user = await fetch_user("tourist")
    assert user is None


@pytest.mark.asyncio
async def test_fetch_user_malformed_json(respx_mock) -> None:
    """Test handling of invalid JSON responses."""
    respx_mock.get("https://codeforces.com/api/user.info?handles=tourist").mock(
        return_value=httpx.Response(
            200,
            content=b"<!DOCTYPE html><html><body>Error</body></html>",
        )
    )

    user = await fetch_user("tourist")
    assert user is None
