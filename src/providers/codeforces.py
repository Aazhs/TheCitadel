"""Codeforces API provider."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger("arena.providers.codeforces")

CODEFORCES_API_BASE = "https://codeforces.com/api"


@dataclass
class CodeforcesUser:
    """A user profile fetched from the Codeforces API."""

    handle: str
    rating: int | None
    max_rating: int | None
    rank: str | None
    max_rank: str | None
    title_photo: str | None
    avatar: str | None


@dataclass
class CodeforcesContest:
    """A contest fetched from the Codeforces API."""

    id: int
    name: str
    type: str
    phase: str
    frozen: bool
    duration_seconds: int
    start_time_seconds: int | None = None


async def fetch_user(handle: str) -> CodeforcesUser | None:
    """Fetch user info from Codeforces API.

    Returns:
        CodeforcesUser object if found, None if the handle is invalid or
        if the API fails/rate limits.
    """
    url = f"{CODEFORCES_API_BASE}/user.info"
    params = {"handles": handle}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            if data.get("status") == "FAILED":
                comment = data.get("comment", "")
                if "Call limit exceeded" in comment:
                    logger.warning("Codeforces API rate limit exceeded when fetching %s", handle)
                else:
                    logger.info("Codeforces API returned FAILED for %s: %s", handle, comment)
                return None

            if data.get("status") != "OK":
                logger.warning("Codeforces API returned unexpected status for %s: %s", handle, data)
                return None

            results = data.get("result", [])
            if not results:
                return None

            user_data = results[0]
            return CodeforcesUser(
                handle=user_data.get("handle", handle),
                rating=user_data.get("rating"),
                max_rating=user_data.get("maxRating"),
                rank=user_data.get("rank"),
                max_rank=user_data.get("maxRank"),
                title_photo=user_data.get("titlePhoto"),
                avatar=user_data.get("avatar"),
            )

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            # Codeforces returns 400 with a JSON payload if handle doesn't exist
            try:
                data = e.response.json()
                if (
                    data.get("status") == "FAILED"
                    and "not found" in data.get("comment", "").lower()
                ):
                    logger.info("Codeforces handle not found: %s", handle)
                    return None
            except ValueError:
                pass
        logger.warning("HTTP error fetching Codeforces user %s: %s", handle, e)
        return None
    except httpx.RequestError as e:
        logger.error("Network error fetching Codeforces user %s: %s", handle, e)
        return None
    except ValueError as e:
        logger.error("JSON decode error fetching Codeforces user %s: %s", handle, e)
        return None
    except Exception as e:
        logger.exception("Unexpected error fetching Codeforces user %s: %s", handle, e)
        return None


async def fetch_contests() -> list[CodeforcesContest] | None:
    """Fetch contest list from Codeforces API.

    Returns:
        A list of CodeforcesContest objects, or None if the API fails.
    """
    url = f"{CODEFORCES_API_BASE}/contest.list"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            data = response.json()

            if data.get("status") == "FAILED":
                comment = data.get("comment", "")
                if "Call limit exceeded" in comment:
                    logger.warning("Codeforces API rate limit exceeded when fetching contests")
                else:
                    logger.warning("Codeforces API returned FAILED for contests: %s", comment)
                return None

            if data.get("status") != "OK":
                logger.warning("Codeforces API returned unexpected status for contests: %s", data)
                return None

            results = data.get("result", [])
            contests = []
            for item in results:
                contests.append(
                    CodeforcesContest(
                        id=item.get("id", 0),
                        name=item.get("name", "Unknown Contest"),
                        type=item.get("type", "UNKNOWN"),
                        phase=item.get("phase", "UNKNOWN"),
                        frozen=item.get("frozen", False),
                        duration_seconds=item.get("durationSeconds", 0),
                        start_time_seconds=item.get("startTimeSeconds"),
                    )
                )
            return contests

    except httpx.HTTPStatusError as e:
        logger.warning("HTTP error fetching Codeforces contests: %s", e)
        return None
    except httpx.RequestError as e:
        logger.error("Network error fetching Codeforces contests: %s", e)
        return None
    except ValueError as e:
        logger.error("JSON decode error fetching Codeforces contests: %s", e)
        return None
    except Exception as e:
        logger.exception("Unexpected error fetching Codeforces contests: %s", e)
        return None
