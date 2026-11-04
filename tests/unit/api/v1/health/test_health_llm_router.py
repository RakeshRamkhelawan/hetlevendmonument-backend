"""Unit tests for health LLM router (src/core/api/v1/health/llm_router.py).

Covers:
- GET /llm
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.routing import APIRoute

from src.core.api.health_endpoints import LLMHealthResponse
from src.core.api.v1.health.llm_router import llm_health_check, router


def test_routes_registered() -> None:
    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/llm" in paths


@pytest.mark.asyncio
async def test_llm_health_check_delegates_to_health_endpoints() -> None:
    fake_response = LLMHealthResponse(
        status="operational",
        providers={},
        default_provider="anthropic",
        message="All providers operational",
    )

    with patch("src.core.api.health_endpoints.llm_health_check", new=AsyncMock(return_value=fake_response)):
        res = await llm_health_check()
        assert res.status == "operational"
        assert res.default_provider == "anthropic"
        assert res.message == "All providers operational"
