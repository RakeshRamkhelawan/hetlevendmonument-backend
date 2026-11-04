import pytest
from unittest.mock import AsyncMock, patch

from src.core.api.v1.focus_builder.agents import agents_router, get_agents


def test_routes_registered() -> None:
    paths = [r.path for r in agents_router.routes]
    assert "/agents" in paths


@pytest.mark.asyncio
async def test_get_agents_success() -> None:
    with patch("src.core.api.v1.focus_builder.agents._get_redis_cache", new_callable=AsyncMock, return_value=None):
        with patch("src.core.api.v1.focus_builder.agents.fetch_live_connections", new_callable=AsyncMock) as mock_ap:
            mock_ap.return_value = [{"appName": "slack"}]
            with patch("src.core.api.v1.focus_builder.agents._set_redis_cache", new_callable=AsyncMock):
                resp = await get_agents(tenant_id=42, current_user=None)
                assert "live" in resp
                assert "internal" in resp
                assert "available" in resp
                assert resp["ap_unavailable"] is False
                assert len(resp["live"]) == 1
                assert resp["live"][0]["id"] == "slack"
                assert resp["live"][0]["category"] == "notification"
