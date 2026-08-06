"""Unit tests for application configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Settings


class TestSettings:
    """Tests for the Settings model."""

    def test_valid_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings loads successfully with a valid DISCORD_TOKEN."""
        monkeypatch.setenv("DISCORD_TOKEN", "test-token-12345")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.discord_token == "test-token-12345"

    def test_default_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ENVIRONMENT defaults to 'development'."""
        monkeypatch.setenv("DISCORD_TOKEN", "test-token")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.environment == "development"

    def test_default_log_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LOG_LEVEL defaults to 'INFO'."""
        monkeypatch.setenv("DISCORD_TOKEN", "test-token")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.log_level == "INFO"

    def test_custom_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ENVIRONMENT can be set to production."""
        monkeypatch.setenv("DISCORD_TOKEN", "test-token")
        monkeypatch.setenv("ENVIRONMENT", "production")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.environment == "production"

    def test_custom_log_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LOG_LEVEL can be overridden."""
        monkeypatch.setenv("DISCORD_TOKEN", "test-token")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.log_level == "DEBUG"

    def test_missing_discord_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing DISCORD_TOKEN must cause a validation error."""
        # Clear the variable if it exists
        monkeypatch.delenv("DISCORD_TOKEN", raising=False)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_invalid_environment_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid ENVIRONMENT value is rejected."""
        monkeypatch.setenv("DISCORD_TOKEN", "test-token")
        monkeypatch.setenv("ENVIRONMENT", "invalid-env")
        with pytest.raises(ValidationError):
            Settings()  # type: ignore[call-arg]

    def test_invalid_log_level_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid LOG_LEVEL value is rejected."""
        monkeypatch.setenv("DISCORD_TOKEN", "test-token")
        monkeypatch.setenv("LOG_LEVEL", "TRACE")
        with pytest.raises(ValidationError):
            Settings()  # type: ignore[call-arg]

    def test_extra_env_vars_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unknown environment variables are silently ignored."""
        monkeypatch.setenv("DISCORD_TOKEN", "test-token")
        monkeypatch.setenv("SOME_RANDOM_VAR", "should-be-ignored")
        settings = Settings()  # type: ignore[call-arg]
        assert not hasattr(settings, "some_random_var")

    def test_case_insensitive_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variable names are case-insensitive."""
        monkeypatch.setenv("discord_token", "lower-case-token")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.discord_token == "lower-case-token"
