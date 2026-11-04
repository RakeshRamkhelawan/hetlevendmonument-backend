"""Unit tests for twin_service_factory._is_eu_only_tenant (B-2 fail-secure fix).

Covers:
  - Happy: eu-only tenant returns True, global tenant returns False
  - Unhappy: DB exception returns True (fail-secure, not fail-open)
  - Behavioral: warning logged on DB error
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.learning.services.twin_service_factory import _is_eu_only_tenant


# ─── Happy path ───────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
class TestIsEuOnlyTenantHappy:
    async def test_eu_only_residency_returns_true(self) -> None:
        db = AsyncMock()
        cursor = MagicMock()
        cursor.scalar_one_or_none = MagicMock(return_value="eu-only")
        db.execute = AsyncMock(return_value=cursor)

        result = await _is_eu_only_tenant(db, tenant_id=1)

        assert result is True

    async def test_global_residency_returns_false(self) -> None:
        db = AsyncMock()
        cursor = MagicMock()
        cursor.scalar_one_or_none = MagicMock(return_value="global")
        db.execute = AsyncMock(return_value=cursor)

        result = await _is_eu_only_tenant(db, tenant_id=2)

        assert result is False

    async def test_no_residency_row_returns_false(self) -> None:
        db = AsyncMock()
        cursor = MagicMock()
        cursor.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=cursor)

        result = await _is_eu_only_tenant(db, tenant_id=3)

        assert result is False


# ─── Unhappy path ─────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
class TestIsEuOnlyTenantUnhappy:
    async def test_returns_true_on_db_error(self) -> None:
        """DB failure must return True (fail-secure: protect eu-only data)."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=Exception("connection refused"))

        result = await _is_eu_only_tenant(db, tenant_id=99)

        assert result is True

    async def test_logs_warning_on_db_error(self) -> None:
        """A warning must be logged when the DB check fails."""
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=RuntimeError("timeout"))

        with patch("src.core.learning.services.twin_service_factory.logger") as mock_logger:
            await _is_eu_only_tenant(db, tenant_id=99)

        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args
        assert "eu_only_check_failed" in call_kwargs[0] or (
            call_kwargs[1].get("error_type") == "RuntimeError" if call_kwargs[1] else True
        )
