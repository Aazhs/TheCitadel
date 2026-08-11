"""Extensive unit tests for the pure scoring engine.

No database, no mocks — just plain function calls against
src.services.scoring.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.services.scoring import (
    DEFAULT_SCORING,
    compute_score,
    get_effective_config,
    parse_rank_bonus_tiers,
    rank_entries,
    validate_config,
)


# ---------------------------------------------------------------------------
# get_effective_config
# ---------------------------------------------------------------------------

class TestGetEffectiveConfig:
    def test_none_returns_defaults(self):
        assert get_effective_config(None) == DEFAULT_SCORING

    def test_none_returns_copy(self):
        cfg = get_effective_config(None)
        cfg["participation_points"] = 999
        assert DEFAULT_SCORING["participation_points"] == 100

    def test_partial_override_merges_correctly(self):
        config = get_effective_config({"participation_points": 50})
        assert config["participation_points"] == 50
        assert config["per_question_points"] == 100  # default kept

    def test_full_override_replaces_all(self):
        overrides = {
            "participation_points": 50,
            "per_question_points": 150,
            "rating_gain_multiplier": 3,
            "rank_bonus_enabled": True,
            "rank_bonus_tiers": [{"max_rank": 10, "bonus": 50}],
        }
        config = get_effective_config(overrides)
        for key, val in overrides.items():
            assert config[key] == val

    def test_unknown_keys_ignored(self):
        config = get_effective_config({"participation_points": 50, "bogus": 123})
        assert "bogus" not in config
        assert config["participation_points"] == 50


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig:
    def test_valid_config_passes(self):
        valid = {
            "participation_points": 50,
            "per_question_points": 150,
            "rating_gain_multiplier": 3,
            "rank_bonus_enabled": True,
            "rank_bonus_tiers": [{"max_rank": 10, "bonus": 50}],
        }
        assert validate_config(valid) == valid

    def test_negative_participation_points_raises(self):
        with pytest.raises(ValueError):
            validate_config({"participation_points": -10})

    def test_negative_per_question_points_raises(self):
        with pytest.raises(ValueError):
            validate_config({"per_question_points": -10})

    def test_negative_rating_gain_multiplier_raises(self):
        with pytest.raises(ValueError):
            validate_config({"rating_gain_multiplier": -1})

    def test_invalid_rank_bonus_tiers_not_list(self):
        with pytest.raises(ValueError):
            validate_config({"rank_bonus_tiers": "not a list"})

    def test_invalid_rank_bonus_tiers_missing_keys(self):
        with pytest.raises(ValueError):
            validate_config({"rank_bonus_tiers": [{"missing": 1}]})

    def test_invalid_rank_bonus_tiers_negative_bonus(self):
        with pytest.raises(ValueError):
            validate_config({"rank_bonus_tiers": [{"max_rank": 10, "bonus": -5}]})

    def test_invalid_rank_bonus_tiers_zero_max_rank(self):
        with pytest.raises(ValueError):
            validate_config({"rank_bonus_tiers": [{"max_rank": 0, "bonus": 50}]})

    def test_valid_rank_bonus_tiers(self):
        cfg = {"rank_bonus_tiers": [{"max_rank": 10, "bonus": 50}]}
        assert validate_config(cfg) == cfg

    def test_empty_overrides_returns_empty_dict(self):
        assert validate_config({}) == {}

    def test_zero_values_are_valid(self):
        cfg = {"participation_points": 0, "per_question_points": 0, "rating_gain_multiplier": 0}
        assert validate_config(cfg) == cfg


# ---------------------------------------------------------------------------
# compute_score
# ---------------------------------------------------------------------------

class TestComputeScore:
    def test_basic_3_solved_no_rating(self):
        sub = {"questions_solved": 3}
        total, bd = compute_score(sub, DEFAULT_SCORING)
        assert total == 400
        assert bd == {
            "participation": 100, "questions": 300,
            "rating_gain": 0, "rank_bonus": 0, "total": 400,
        }

    def test_zero_questions_participation_only(self):
        total, bd = compute_score({"questions_solved": 0}, DEFAULT_SCORING)
        assert total == 100
        assert bd["participation"] == 100
        assert bd["questions"] == 0

    def test_positive_rating_gain(self):
        sub = {
            "questions_solved": 3,
            "claimed_rating_before": 1200,
            "claimed_rating_after": 1250,
        }
        total, bd = compute_score(sub, DEFAULT_SCORING)
        assert bd["rating_gain"] == 100  # 50 * 2
        assert total == 500  # 100 + 300 + 100

    def test_negative_rating_gain_zero_points(self):
        sub = {
            "questions_solved": 3,
            "claimed_rating_before": 1250,
            "claimed_rating_after": 1200,
        }
        total, bd = compute_score(sub, DEFAULT_SCORING)
        assert bd["rating_gain"] == 0
        assert total == 400

    def test_zero_rating_delta(self):
        sub = {
            "questions_solved": 3,
            "claimed_rating_before": 1200,
            "claimed_rating_after": 1200,
        }
        _, bd = compute_score(sub, DEFAULT_SCORING)
        assert bd["rating_gain"] == 0

    def test_none_ratings(self):
        _, bd = compute_score({"questions_solved": 3}, DEFAULT_SCORING)
        assert bd["rating_gain"] == 0

    def test_only_before_rating(self):
        sub = {"questions_solved": 3, "claimed_rating_before": 1200}
        _, bd = compute_score(sub, DEFAULT_SCORING)
        assert bd["rating_gain"] == 0

    def test_rank_bonus_disabled_by_default(self):
        sub = {"questions_solved": 3, "claimed_rank": 5}
        _, bd = compute_score(sub, DEFAULT_SCORING)
        assert bd["rank_bonus"] == 0

    def test_rank_bonus_enabled_within_tier(self):
        cfg = get_effective_config({
            "rank_bonus_enabled": True,
            "rank_bonus_tiers": [{"max_rank": 10, "bonus": 200}, {"max_rank": 50, "bonus": 100}],
        })
        sub = {"questions_solved": 3, "claimed_rank": 5}
        total, bd = compute_score(sub, cfg)
        assert bd["rank_bonus"] == 200
        assert total == 600

    def test_rank_bonus_enabled_second_tier(self):
        cfg = get_effective_config({
            "rank_bonus_enabled": True,
            "rank_bonus_tiers": [{"max_rank": 10, "bonus": 200}, {"max_rank": 50, "bonus": 100}],
        })
        sub = {"questions_solved": 3, "claimed_rank": 25}
        _, bd = compute_score(sub, cfg)
        assert bd["rank_bonus"] == 100

    def test_rank_bonus_outside_all_tiers(self):
        cfg = get_effective_config({
            "rank_bonus_enabled": True,
            "rank_bonus_tiers": [{"max_rank": 10, "bonus": 200}],
        })
        sub = {"questions_solved": 3, "claimed_rank": 15}
        _, bd = compute_score(sub, cfg)
        assert bd["rank_bonus"] == 0

    def test_rank_bonus_enabled_rank_none(self):
        cfg = get_effective_config({
            "rank_bonus_enabled": True,
            "rank_bonus_tiers": [{"max_rank": 10, "bonus": 200}],
        })
        sub = {"questions_solved": 3}
        _, bd = compute_score(sub, cfg)
        assert bd["rank_bonus"] == 0

    def test_custom_config_values(self):
        cfg = get_effective_config({
            "participation_points": 50,
            "per_question_points": 200,
        })
        sub = {"questions_solved": 3}
        total, bd = compute_score(sub, cfg)
        assert bd["participation"] == 50
        assert bd["questions"] == 600
        assert total == 650


# ---------------------------------------------------------------------------
# rank_entries
# ---------------------------------------------------------------------------

class TestRankEntries:
    def test_single_entry_rank_1(self):
        entries = [{"total_points": 100, "discord_user_id": "1"}]
        ranked = rank_entries(entries)
        assert ranked[0]["rank"] == 1

    def test_different_points(self):
        entries = [
            {"total_points": 100, "discord_user_id": "1"},
            {"total_points": 200, "discord_user_id": "2"},
        ]
        ranked = rank_entries(entries)
        assert ranked[0]["discord_user_id"] == "2"
        assert ranked[0]["rank"] == 1

    def test_tiebreak_questions_solved(self):
        entries = [
            {"total_points": 100, "questions_solved": 1, "discord_user_id": "1"},
            {"total_points": 100, "questions_solved": 3, "discord_user_id": "2"},
        ]
        ranked = rank_entries(entries)
        assert ranked[0]["discord_user_id"] == "2"

    def test_tiebreak_rating_gain(self):
        entries = [
            {"total_points": 100, "questions_solved": 2, "rating_gain": 10, "discord_user_id": "1"},
            {"total_points": 100, "questions_solved": 2, "rating_gain": 50, "discord_user_id": "2"},
        ]
        ranked = rank_entries(entries)
        assert ranked[0]["discord_user_id"] == "2"

    def test_tiebreak_submitted_at(self):
        now = datetime.now(UTC)
        entries = [
            {"total_points": 100, "questions_solved": 2, "rating_gain": 10,
             "submitted_at": now, "discord_user_id": "1"},
            {"total_points": 100, "questions_solved": 2, "rating_gain": 10,
             "submitted_at": now - timedelta(minutes=5), "discord_user_id": "2"},
        ]
        ranked = rank_entries(entries)
        assert ranked[0]["discord_user_id"] == "2"  # earlier

    def test_tiebreak_discord_user_id(self):
        now = datetime.now(UTC)
        entries = [
            {"total_points": 100, "questions_solved": 2, "rating_gain": 10,
             "submitted_at": now, "discord_user_id": "200"},
            {"total_points": 100, "questions_solved": 2, "rating_gain": 10,
             "submitted_at": now, "discord_user_id": "100"},
        ]
        ranked = rank_entries(entries)
        assert ranked[0]["discord_user_id"] == "100"

    def test_all_identical_stable_by_user_id(self):
        now = datetime.now(UTC)
        entries = [
            {"total_points": 100, "questions_solved": 1, "rating_gain": 0,
             "submitted_at": now, "discord_user_id": "3"},
            {"total_points": 100, "questions_solved": 1, "rating_gain": 0,
             "submitted_at": now, "discord_user_id": "1"},
            {"total_points": 100, "questions_solved": 1, "rating_gain": 0,
             "submitted_at": now, "discord_user_id": "2"},
        ]
        ranked = rank_entries(entries)
        assert [e["discord_user_id"] for e in ranked] == ["1", "2", "3"]

    def test_empty_list(self):
        assert rank_entries([]) == []

    def test_large_list_various_ties(self):
        now = datetime.now(UTC)
        entries = [
            {"total_points": 100, "questions_solved": 2, "rating_gain": 0,
             "submitted_at": now, "discord_user_id": "1"},
            {"total_points": 200, "questions_solved": 1, "rating_gain": 0,
             "submitted_at": now, "discord_user_id": "2"},
            {"total_points": 100, "questions_solved": 2, "rating_gain": 10,
             "submitted_at": now, "discord_user_id": "3"},
            {"total_points": 100, "questions_solved": 2, "rating_gain": 10,
             "submitted_at": now - timedelta(minutes=1), "discord_user_id": "4"},
            {"total_points": 100, "questions_solved": 2, "rating_gain": 10,
             "submitted_at": now - timedelta(minutes=1), "discord_user_id": "5"},
        ]
        ranked = rank_entries(entries)
        ids = [e["discord_user_id"] for e in ranked]
        assert ids == ["2", "4", "5", "3", "1"]

    def test_cascading_tiebreak_all_levels(self):
        now = datetime.now(UTC)
        entries = [
            {"total_points": 100, "questions_solved": 1, "rating_gain": 10,
             "submitted_at": now, "discord_user_id": "B"},
            {"total_points": 100, "questions_solved": 1, "rating_gain": 10,
             "submitted_at": now, "discord_user_id": "A"},
        ]
        ranked = rank_entries(entries)
        assert ranked[0]["discord_user_id"] == "A"
        assert ranked[0]["rank"] == 1
        assert ranked[1]["rank"] == 2


# ---------------------------------------------------------------------------
# parse_rank_bonus_tiers
# ---------------------------------------------------------------------------

class TestParseRankBonusTiers:
    def test_valid_two_tiers(self):
        tiers = parse_rank_bonus_tiers("10:200,50:100")
        assert tiers == [{"max_rank": 10, "bonus": 200}, {"max_rank": 50, "bonus": 100}]

    def test_single_tier(self):
        tiers = parse_rank_bonus_tiers("10:200")
        assert tiers == [{"max_rank": 10, "bonus": 200}]

    def test_whitespace_handling(self):
        tiers = parse_rank_bonus_tiers("  10 : 200 , 50 : 100  ")
        assert tiers == [{"max_rank": 10, "bonus": 200}, {"max_rank": 50, "bonus": 100}]

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_rank_bonus_tiers("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            parse_rank_bonus_tiers("   ")

    def test_invalid_separator_raises(self):
        with pytest.raises(ValueError):
            parse_rank_bonus_tiers("10-200")

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError):
            parse_rank_bonus_tiers("abc:200")

    def test_trailing_comma_raises(self):
        with pytest.raises(ValueError):
            parse_rank_bonus_tiers("10:200,")

    def test_negative_bonus_raises(self):
        with pytest.raises(ValueError):
            parse_rank_bonus_tiers("10:-5")

    def test_zero_max_rank_raises(self):
        with pytest.raises(ValueError):
            parse_rank_bonus_tiers("0:200")
