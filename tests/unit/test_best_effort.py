"""Tests for best_effort context manager."""

import pytest
from unittest.mock import AsyncMock

from src.core.utils.best_effort import best_effort


class TestBestEffort:
    """Test best_effort context manager for non-critical operations."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_best_effort_succeeds_without_exception(self):
        """best_effort should allow exception-free code to complete normally."""
        operation_ran = False

        async with best_effort("test operation"):
            operation_ran = True

        assert operation_ran is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_best_effort_catches_exception(self, caplog):
        """best_effort must catch and log exceptions without re-raising."""
        operation_ran = False

        async with best_effort("test operation"):
            operation_ran = True
            raise ValueError("Test error")

        assert operation_ran is True
        assert "Test error" in caplog.text

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_best_effort_with_db_session_rollback_on_success(self):
        """best_effort should not rollback DB session on success."""
        db_session = AsyncMock()

        async with best_effort("test operation", db_session=db_session):
            pass

        db_session.rollback.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_best_effort_with_db_session_rollback_on_failure(self, caplog):
        """best_effort must rollback DB session when operation fails."""
        db_session = AsyncMock()

        async with best_effort("test operation", db_session=db_session):
            raise ValueError("Test error")

        db_session.rollback.assert_called_once()
        assert "Test error" in caplog.text

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_best_effort_without_db_session(self, caplog):
        """best_effort should handle None db_session gracefully."""
        async with best_effort("test operation", db_session=None):
            raise ValueError("Test error")

        assert "Test error" in caplog.text

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_best_effort_db_session_type_annotation(self):
        """best_effort must accept AsyncSession | None parameter."""
        db_session = AsyncMock()

        async with best_effort("test", db_session=db_session):
            pass

        db_session.rollback.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_best_effort_rollback_failure_logs_warning(self, caplog):
        """best_effort must catch rollback failures and log as warning."""
        db_session = AsyncMock()
        db_session.rollback.side_effect = RuntimeError("Rollback failed")

        async with best_effort("test operation", db_session=db_session):
            raise ValueError("Original error")

        assert "rollback after test operation also failed" in caplog.text
