"""CodeChef API provider for contest discovery and profile validation."""

import logging
from dataclasses import dataclass
from datetime import datetime, UTC

import httpx

logger = logging.getLogger("arena.providers.codechef")


@dataclass
class CodeChefContest:
    """Represents an upcoming or active CodeChef contest."""
    code: str
    name: str
    start_time_utc: datetime
    end_time_utc: datetime
    duration_minutes: int


@dataclass
class CodeChefUser:
    """Represents a CodeChef user profile."""
    handle: str
    rating: int | None = None
    max_rating: int | None = None
    rank: str | None = None
    stars: int | None = None


async def fetch_user(handle: str) -> CodeChefUser | None:
    """
    Fetch a CodeChef user profile by scraping the public profile page.
    CodeChef does not provide an official public API for user profiles,
    so we extract the rating and max rating from the HTML.
    """
    import re
    url = f"https://www.codechef.com/users/{handle}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AlgorithmArenaBot/1.0)",
        "Accept": "text/html",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                return None
            
            html = response.text
            
            rating = None
            max_rating = None
            
            rating_match = re.search(r'class="rating-number">\s*(\d+)', html)
            if rating_match:
                rating = int(rating_match.group(1))
                
            max_rating_match = re.search(r'\(Highest Rating (\d+)\)', html)
            if max_rating_match:
                max_rating = int(max_rating_match.group(1))
                
            stars = None
            if rating is not None:
                if rating < 1400:
                    stars = 1
                elif rating < 1600:
                    stars = 2
                elif rating < 1800:
                    stars = 3
                elif rating < 2000:
                    stars = 4
                elif rating < 2200:
                    stars = 5
                elif rating < 2500:
                    stars = 6
                else:
                    stars = 7
                
            return CodeChefUser(handle=handle, rating=rating, max_rating=max_rating, stars=stars)
            
    except Exception as e:
        logger.error("Error fetching CodeChef user %s: %s", handle, e)
        return None


async def fetch_contests() -> list[CodeChefContest] | None:
    """Fetch all upcoming and present contests from CodeChef."""
    url = "https://www.codechef.com/api/list/contests/all"
    
    # We use a user agent to prevent basic blocking
    headers = {
        "User-Agent": "AlgorithmArenaBot/1.0",
        "Accept": "application/json",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            contests = []
            
            # CodeChef returns future_contests and present_contests
            for category in ["future_contests", "present_contests"]:
                for c in data.get(category, []):
                    try:
                        # Format: "08 Aug 2026 14:30:00"
                        # Note: CodeChef API typically returns times in IST (Indian Standard Time). 
                        start_str = c.get("contest_start_date")
                        end_str = c.get("contest_end_date")
                        
                        if not start_str or not end_str:
                            continue
                            
                        # Parse naive datetime
                        start_dt = datetime.strptime(start_str, "%d %b %Y %H:%M:%S")
                        end_dt = datetime.strptime(end_str, "%d %b %Y %H:%M:%S")
                        
                        # Apply IST timezone (UTC+5:30) and convert to UTC
                        from datetime import timezone, timedelta
                        ist = timezone(timedelta(hours=5, minutes=30))
                        start_dt = start_dt.replace(tzinfo=ist).astimezone(UTC)
                        end_dt = end_dt.replace(tzinfo=ist).astimezone(UTC)
                            
                        contests.append(CodeChefContest(
                            code=c.get("contest_code", ""),
                            name=c.get("contest_name", ""),
                            start_time_utc=start_dt,
                            end_time_utc=end_dt,
                            duration_minutes=int(c.get("contest_duration", 0))
                        ))
                    except Exception as e:
                        logger.warning("Error parsing CodeChef contest %s: %s", c.get("contest_code"), e)
                        
            return contests
            
    except Exception as e:
        logger.error("Error fetching CodeChef contests: %s", e)
        return None
