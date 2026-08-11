"""Rating calculation engine for Competitive Programming and DSA systems."""

import logging
from typing import Sequence

from src.db.models import LinkedAccount
from src.providers.leetcode import fetch_user_stats

logger = logging.getLogger("arena.services.ratings")

def _get_star_tier(rating: int, is_dsa: bool = False) -> int:
    """Map a rating score to a 1-5 star tier."""
    if rating == 0:
        return 0
    if rating < 1400:
        return 1
    elif rating < 1600:
        return 2
    elif rating < (1800 if is_dsa else 1900):
        return 3
    elif rating < 2100:
        return 4
    else:
        return 5

def calculate_cp_rating(accounts: Sequence[LinkedAccount]) -> int:
    """Calculate the CP rating across all linked platforms.
    
    Anchor: CodeChef
    Normalizations: 
    - CodeChef: +0
    - Codeforces: +100
    - LeetCode: -300
    
    Formula: Max normalized rating across all platforms.
    Bonus: +50 if ratings exist on multiple platforms.
    """
    valid_ratings = []
    
    for account in accounts:
        if account.current_rating is None:
            continue
            
        rating = account.current_rating
        platform = account.platform.lower()
        
        if platform == "codechef":
            valid_ratings.append(rating)
        elif platform == "codeforces":
            valid_ratings.append(rating + 100)
        elif platform == "leetcode":
            valid_ratings.append(rating - 300)

    if not valid_ratings:
        return 0

    base_score = max(valid_ratings)
    
    # Add bonus if multiple platforms are rated
    if len(valid_ratings) > 1:
        base_score += 50
        
    return base_score

async def calculate_dsa_rating(accounts: Sequence[LinkedAccount]) -> int:
    """Calculate the DSA rating across all linked platforms.
    
    Anchor: LeetCode
    Normalizations:
    - LeetCode: +0
    - CodeChef: +300
    - Codeforces: +400
    
    Formula: Max normalized rating. 
    Fallback: If LeetCode is linked but unrated, estimate using problem counts:
              1000 + (1*Easy) + (3*Medium) + (5*Hard)
    """
    valid_ratings = []
    
    for account in accounts:
        if account.current_rating is None:
            continue
            
        rating = account.current_rating
        platform = account.platform.lower()
        
        if platform == "leetcode":
            valid_ratings.append(rating)
        elif platform == "codechef":
            valid_ratings.append(rating + 300)
        elif platform == "codeforces":
            valid_ratings.append(rating + 400)

    # Check for unrated LeetCode estimation
    lc_account = next((a for a in accounts if a.platform.lower() == "leetcode"), None)
    if lc_account and lc_account.current_rating is None:
        stats = await fetch_user_stats(lc_account.handle)
        if stats:
            estimated_rating = 1000 + (stats.easy_solved * 1) + (stats.medium_solved * 3) + (stats.hard_solved * 5)
            # Use rating from stats if it exists (in case it just wasn't synced locally)
            if stats.rating:
                estimated_rating = max(estimated_rating, stats.rating)
            valid_ratings.append(estimated_rating)

    if not valid_ratings:
        return 0

    return max(valid_ratings)

async def compute_member_star_ratings(accounts: Sequence[LinkedAccount]) -> tuple[int, int]:
    """Compute and return the (CP Star Rating, DSA Star Rating) for a member's accounts.
    
    Returns:
        tuple[int, int]: (cp_stars, dsa_stars) where stars are 0-5.
    """
    cp_score = calculate_cp_rating(accounts)
    dsa_score = await calculate_dsa_rating(accounts)
    
    return _get_star_tier(cp_score, is_dsa=False), _get_star_tier(dsa_score, is_dsa=True)
