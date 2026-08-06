"""Unit tests for the database health-check service — uses mocks, no live DB required."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.db_health import DbHealthResult, check_db_health


class TestDbHealthResult:
    """Tests for the DbHealthResult dataclass."""

    def test_healthy_result(self) -> None:
        result = DbHealthResult(
            healthy=True,
            latency_ms=1.5,
            server_version="PostgreSQL 15.4",
        )
        assert result.healthy is True
        assert result.latency_ms == 1.5
        assert result.server_version == "PostgreSQL 15.4"
        assert result.error is None

    def test_unhealthy_result(self) -> None:
        result = DbHealthResult(
            healthy=False,
            latency_ms=100.0,
            server_version="unknown",
            error="Connection refused",
        )
        assert result.healthy is False
        assert result.error == "Connection refused"

    def test_frozen(self) -> None:
        result = DbHealthResult(healthy=True, latency_ms=1.0, server_version="PG 15")
        with pytest.raises(AttributeError):
            result.healthy = False  # type: ignore[misc]


class TestCheckDbHealth:
    """Tests for the check_db_health async function."""

    @pytest.mark.asyncio
    async def test_healthy_connection(self) -> None:
        """Mocked engine returns a valid version string."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = "PostgreSQL 15.4 on x86_64"

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_result)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("src.services.db_health.get_engine", return_value=mock_engine):
            result = await check_db_health()

        assert result.healthy is True
        assert result.latency_ms >= 0
        assert "PostgreSQL" in result.server_version
        assert result.error is None

    @pytest.mark.asyncio
    async def test_connection_failure(self) -> None:
        """Mocked engine raises an exception."""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=ConnectionRefusedError("refused"))
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("src.services.db_health.get_engine", return_value=mock_engine):
            result = await check_db_health()

        assert result.healthy is False
        assert result.server_version == "unknown"
        assert result.error is not None
        assert "refused" in result.error

    @pytest.mark.asyncio
    async def test_engine_not_initialised(self) -> None:
        """get_engine raises RuntimeError when DB is not initialised."""
        with patch(
            "src.services.db_health.get_engine",
            side_effect=RuntimeError("not initialised"),
        ):
            result = await check_db_health()

        assert result.healthy is False
        assert "not initialised" in (result.error or "")
