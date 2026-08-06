"""Application configuration using Pydantic Settings.

All configuration is loaded from environment variables. Required variables
will cause a clear validation error at startup if missing.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Bot configuration validated from environment variables."""

    # Required
    discord_token: str

    # Database — required for full functionality
    database_url: str | None = None

    # Optional with safe defaults
    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings.

    Uses lru_cache so the .env file is read once and the same
    Settings instance is reused for the lifetime of the process.
    """
    return Settings()  # type: ignore[call-arg]
