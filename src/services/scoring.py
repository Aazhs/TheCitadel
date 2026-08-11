"""Pure scoring engine for Algorithm Arena events.

All functions operate on plain dicts — no database or ORM imports.
This keeps the scoring logic trivially testable.
"""

from __future__ import annotations

import datetime


DEFAULT_SCORING: dict = {
    "participation_points": 100,
    "per_question_points": 100,
    "rating_gain_multiplier": 2,
    "rank_bonus_enabled": False,
    "rank_bonus_tiers": [],  # [{"max_rank": 10, "bonus": 200}, ...]
}


def get_effective_config(event_points_config: dict | None) -> dict:
    """Get the effective scoring config by merging overrides onto defaults.

    Args:
        event_points_config: A dictionary of overrides, or None.

    Returns:
        The merged scoring configuration dict.  Unknown keys in *overrides*
        are **not** carried through — only keys present in DEFAULT_SCORING.
    """
    config = DEFAULT_SCORING.copy()
    if event_points_config:
        for key in DEFAULT_SCORING:
            if key in event_points_config:
                config[key] = event_points_config[key]
    return config


def validate_config(overrides: dict) -> dict:
    """Validate and clean a scoring config overrides dictionary.

    Validates that numeric values are non-negative.  If rank_bonus_tiers is
    present it must be a list of dicts with ``max_rank`` (int > 0) and
    ``bonus`` (int >= 0).

    Args:
        overrides: The dictionary of config overrides to validate.

    Returns:
        A cleaned dictionary containing only the valid keys.

    Raises:
        ValueError: If any provided value fails validation.
    """
    cleaned: dict = {}
    valid_keys = set(DEFAULT_SCORING)

    for key, value in overrides.items():
        if key not in valid_keys:
            continue

        if key in ("participation_points", "per_question_points", "rating_gain_multiplier"):
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"{key} must be a non-negative number.")
            cleaned[key] = value

        elif key == "rank_bonus_enabled":
            if not isinstance(value, bool):
                raise ValueError("rank_bonus_enabled must be a boolean.")
            cleaned[key] = value

        elif key == "rank_bonus_tiers":
            if not isinstance(value, list):
                raise ValueError("rank_bonus_tiers must be a list.")
            for tier in value:
                if not isinstance(tier, dict):
                    raise ValueError("Each rank bonus tier must be a dict.")
                max_rank = tier.get("max_rank")
                bonus = tier.get("bonus")
                if not isinstance(max_rank, int) or max_rank <= 0:
                    raise ValueError("tier max_rank must be an integer > 0.")
                if not isinstance(bonus, int) or bonus < 0:
                    raise ValueError("tier bonus must be a non-negative integer.")
            cleaned[key] = value

    return cleaned


def compute_score(submission_data: dict, config: dict) -> tuple[int, dict]:
    """Compute the score for a single submission.

    Args:
        submission_data: A dict with keys ``questions_solved``,
            ``claimed_rating_before``, ``claimed_rating_after``,
            ``claimed_rank``.
        config: The effective scoring configuration (from
            :func:`get_effective_config`).

    Returns:
        ``(total_points, breakdown)`` where *breakdown* is a dict with keys
        ``participation``, ``questions``, ``rating_gain``, ``rank_bonus``,
        and ``total``.
    """
    participation = int(config["participation_points"])

    questions_solved = submission_data.get("questions_solved", 0)
    questions = questions_solved * int(config["per_question_points"])

    rating_gain = 0
    before = submission_data.get("claimed_rating_before")
    after = submission_data.get("claimed_rating_after")
    if before is not None and after is not None:
        delta = after - before
        if delta > 0:
            rating_gain = int(delta * config["rating_gain_multiplier"])

    rank_bonus = 0
    claimed_rank = submission_data.get("claimed_rank")
    if config.get("rank_bonus_enabled") and claimed_rank is not None:
        tiers = sorted(config.get("rank_bonus_tiers", []), key=lambda t: t["max_rank"])
        for tier in tiers:
            if claimed_rank <= tier["max_rank"]:
                rank_bonus = tier["bonus"]
                break

    total = participation + questions + rating_gain + rank_bonus

    breakdown = {
        "participation": participation,
        "questions": questions,
        "rating_gain": rating_gain,
        "rank_bonus": rank_bonus,
        "total": total,
    }
    return total, breakdown


def rank_entries(entries: list[dict]) -> list[dict]:
    """Rank a list of scored entries with 4-level tie-breaking.

    Sort order (all ties broken in sequence):
      1. ``total_points`` DESC
      2. ``questions_solved`` DESC
      3. ``rating_gain`` DESC
      4. ``submitted_at`` ASC  (earlier is better)
      5. ``discord_user_id`` ASC  (stable)

    Each entry receives a ``rank`` key (1-based).

    Args:
        entries: A list of dicts.  Each **must** have ``total_points``;
            the remaining keys are optional and default to 0 / max-datetime /
            empty string.

    Returns:
        The sorted list with ``rank`` assigned.
    """

    def _sort_key(entry: dict) -> tuple:
        submitted_at = entry.get("submitted_at")
        if isinstance(submitted_at, str):
            submitted_at = datetime.datetime.fromisoformat(
                submitted_at.replace("Z", "+00:00")
            )
        elif submitted_at is None:
            submitted_at = datetime.datetime.max

        return (
            -entry.get("total_points", 0),
            -entry.get("questions_solved", 0),
            -entry.get("rating_gain", 0),
            submitted_at,
            str(entry.get("discord_user_id", "")),
        )

    sorted_entries = sorted(entries, key=_sort_key)
    for i, entry in enumerate(sorted_entries):
        entry["rank"] = i + 1
    return sorted_entries


def parse_rank_bonus_tiers(tiers_str: str) -> list[dict]:
    """Parse a rank bonus tiers string into a list of tier dicts.

    Args:
        tiers_str: A comma-separated string like ``"10:200,50:100"``.

    Returns:
        ``[{"max_rank": 10, "bonus": 200}, {"max_rank": 50, "bonus": 100}]``

    Raises:
        ValueError: If the string is empty or the format is invalid.
    """
    stripped = tiers_str.strip()
    if not stripped:
        raise ValueError("Tier string must not be empty.")

    tiers: list[dict] = []
    for part in stripped.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"Empty tier segment in '{tiers_str}'.")
        if ":" not in part:
            raise ValueError(f"Invalid tier format '{part}'. Expected 'max_rank:bonus'.")
        try:
            rank_str, bonus_str = part.split(":")
            max_rank = int(rank_str.strip())
            bonus = int(bonus_str.strip())
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Invalid tier format '{part}'. Expected 'max_rank:bonus'."
            ) from exc
        if max_rank <= 0 or bonus < 0:
            raise ValueError(
                f"Invalid tier values in '{part}': max_rank must be > 0, bonus >= 0."
            )
        tiers.append({"max_rank": max_rank, "bonus": bonus})
    return tiers
