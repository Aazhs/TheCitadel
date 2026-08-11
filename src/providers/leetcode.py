"""LeetCode API provider for fetching user stats (ratings and problem counts)."""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger("arena.providers.leetcode")


@dataclass
class LeetCodeUserStats:
    """Statistics for a LeetCode user."""
    handle: str
    rating: int | None
    easy_solved: int
    medium_solved: int
    hard_solved: int
    global_rank: int | None = None


async def fetch_user_stats(handle: str) -> LeetCodeUserStats | None:
    """Fetch user stats and rating from LeetCode GraphQL API."""
    url = "https://leetcode.com/graphql"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AlgorithmArenaBot/1.0",
    }
    
    # We query both the profile (for solved counts) and contest history (for rating)
    query = """
    query getUserStats($handle: String!) {
      matchedUser(username: $handle) {
        submitStats {
          acSubmissionNum {
            difficulty
            count
          }
        }
      }
      userContestRanking(username: $handle) {
        rating
        globalRanking
      }
    }
    """
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url, 
                json={"query": query, "variables": {"handle": handle}},
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                logger.info("LeetCode API returned errors for %s: %s", handle, data["errors"])
                return None
                
            result_data = data.get("data", {})
            matched_user = result_data.get("matchedUser")
            
            if not matched_user:
                return None
                
            # Extract solved counts
            easy = medium = hard = 0
            submissions = matched_user.get("submitStats", {}).get("acSubmissionNum", [])
            for sub in submissions:
                diff = sub.get("difficulty")
                count = sub.get("count", 0)
                if diff == "Easy":
                    easy = count
                elif diff == "Medium":
                    medium = count
                elif diff == "Hard":
                    hard = count
                    
            # Extract rating
            rating = None
            global_rank = None
            contest_ranking = result_data.get("userContestRanking")
            if contest_ranking:
                if contest_ranking.get("rating"):
                    rating = int(float(contest_ranking["rating"]))
                if contest_ranking.get("globalRanking"):
                    global_rank = contest_ranking["globalRanking"]
                
            return LeetCodeUserStats(
                handle=handle,
                rating=rating,
                easy_solved=easy,
                medium_solved=medium,
                hard_solved=hard,
                global_rank=global_rank,
            )
            
    except Exception as e:
        logger.warning("Error fetching LeetCode stats for %s: %s", handle, e)
        return None

@dataclass
class LeetCodeContest:
    """Represents a LeetCode contest."""
    title_slug: str
    title: str
    start_time_utc: int # Using timestamp internally or datetime? The struct uses int for raw, but let's use datetime
    duration_seconds: int

async def fetch_contests() -> list[LeetCodeContest] | None:
    """Fetch all upcoming and present contests from LeetCode."""
    url = "https://leetcode.com/graphql"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AlgorithmArenaBot/1.0",
    }
    
    query = """
    query {
      allContests {
        title
        titleSlug
        startTime
        duration
      }
    }
    """
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url, 
                json={"query": query},
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                logger.error("LeetCode API returned errors: %s", data["errors"])
                return None
                
            contests_data = data.get("data", {}).get("allContests", [])
            
            contests = []
            for c in contests_data:
                # Filter out old contests (or we can return all and let the syncer handle it, but it's better to just return what they give us)
                contests.append(LeetCodeContest(
                    title_slug=c.get("titleSlug"),
                    title=c.get("title"),
                    start_time_utc=c.get("startTime"),
                    duration_seconds=c.get("duration")
                ))
            return contests
            
    except Exception as e:
        logger.error("Error fetching LeetCode contests: %s", e)
        return None
