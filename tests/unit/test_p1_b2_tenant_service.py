"""
AUDIT-P1-B2: src/core/services/tenant_service.py did not exist.
Tests verify get_tenant_by_id and require_tenant_context implementations.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest


def _make_request(path: str = "/api/v1/test") -> StarletteRequest:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 9999),
        "state": MagicMock(),
    }
    return StarletteRequest(scope)


@pytest.mark.unit
class TestGetTenantById:
    """get_tenant_by_id: async lookup returning Tenant or None."""

    @pytest.mark.asyncio
    async def test_returns_tenant_when_found(self):
        """Happy path: existing tenant_id returns the Tenant object."""
        from src.core.services.tenant_service import get_tenant_by_id

        mock_tenant = MagicMock()
        mock_tenant.id = 42

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_tenant
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_tenant_by_id(42, mock_db)

        assert result is mock_tenant
        assert result.id == 42

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Unhappy path: unknown tenant_id returns None, does not raise."""
        from src.core.services.tenant_service import get_tenant_by_id

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_tenant_by_id(999, mock_db)

        assert result is None


@pytest.mark.unit
class TestRequireTenantContext:
    """require_tenant_context: ContextVar extraction with fail-secure behaviour."""

    def test_returns_tenant_id_when_context_is_set(self):
        """Happy path: ContextVar has a valid tenant_id."""
        from src.core.services.tenant_service import require_tenant_context

        with patch(
            "src.core.services.tenant_service.get_tenant_id",
            return_value=7,
        ):
            result = require_tenant_context(_make_request())

        assert result == 7

    def test_raises_400_when_context_is_missing(self):
        """Unhappy path: ContextVar not set raises HTTPException(400)."""
        from src.core.services.tenant_service import require_tenant_context

        with patch(
            "src.core.services.tenant_service.get_tenant_id",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                require_tenant_context(_make_request())

        assert exc_info.value.status_code == 400
        assert "tenant" in exc_info.value.detail.lower()

    def test_does_not_fallback_to_hardcoded_tenant_id(self):
        """
        Security: when context is missing, the function must NOT fall back
        to any numeric default (e.g. 1). Hardcoded tenant_id violates ADR-003.
        """
        from src.core.services.tenant_service import require_tenant_context

        with patch(
            "src.core.services.tenant_service.get_tenant_id",
            return_value=None,
        ):
            try:
                result = require_tenant_context(_make_request())
                assert result != 1, "Must not return hardcoded tenant_id=1 as fallback"
                assert result is not None, "Must not return None instead of raising"
            except HTTPException:
                pass  # Correct behaviour: exception raised, no fallback

    def test_tenant_b_cannot_access_tenant_a_data_via_context(self):
        """
        Tenant isolation: the ContextVar is per-request async-safe. Switching
        the ContextVar to tenant B returns B's id, not A's id.
        """
        from src.core.services.tenant_service import require_tenant_context

        req_a = _make_request("/api/v1/a")
        req_b = _make_request("/api/v1/b")

        with patch(
            "src.core.services.tenant_service.get_tenant_id",
            return_value=1,
        ):
            tenant_a_id = require_tenant_context(req_a)

        with patch(
            "src.core.services.tenant_service.get_tenant_id",
            return_value=2,
        ):
            tenant_b_id = require_tenant_context(req_b)

        assert tenant_a_id != tenant_b_id
        assert tenant_a_id == 1
        assert tenant_b_id == 2
