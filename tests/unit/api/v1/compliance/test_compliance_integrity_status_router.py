"""Unit tests for compliance integrity status router (src/core/api/v1/compliance/integrity_status_router.py).

Covers:
- GET /integrity/status
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.routing import APIRoute
from starlette.requests import Request

from src.core.api.v1.compliance.integrity_status_router import (
    get_chain_status,
    integrity_status_router,
)


class DummyUser:
    def __init__(self, id: int = 1, tenant_id: int = 42) -> None:
        self.id = id
        self.tenant_id = tenant_id


def _create_mock_request() -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/integrity/status",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_routes_registered() -> None:
    routes = [r for r in integrity_status_router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/integrity/status" in paths


@pytest.mark.asyncio
async def test_get_chain_status_success() -> None:
    user = DummyUser(id=1, tenant_id=42)
    req = _create_mock_request()

    verifier = AsyncMock()
    mock_result = MagicMock()
    mock_result.status = "healthy"
    mock_result.last_verified_at = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    mock_result.total_entries = 100
    mock_result.broken_entries_count = 0
    mock_result.unhashed_entries = 0
    mock_result.health_percentage = 100.0
    mock_result.tenant_id = 42
    verifier.get_chain_status.return_value = mock_result

    resp = await get_chain_status(
        request=req,
        current_user=user,
        verifier=verifier,
    )
    assert resp.status == "healthy"
    assert resp.total_entries == 100
    assert resp.broken_entries_count == 0
    assert resp.tenant_id == 42
