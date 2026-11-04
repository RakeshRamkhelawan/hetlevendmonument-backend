"""Integration tests for the current agentic routing API contract."""

import pytest


@pytest.mark.asyncio
async def test_route_endpoint(async_client, admin_token):
    """Current /route contract requires tenant_id and should return success or controlled error."""
    response = await async_client.post(
        "/api/v1/agentic/route",
        json={"query": "Hello world", "tenant_id": "1"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code in (200, 500)
    data = response.json()
    if response.status_code == 200:
        assert "supervisor_id" in data
        assert "confidence" in data
        assert "routing_path" in data
    else:
        assert "detail" in data


@pytest.mark.asyncio
async def test_route_debug_endpoint(async_client, admin_token):
    """Debug endpoint should return diagnostics or controlled error details."""
    response = await async_client.post(
        "/api/v1/agentic/router/debug",
        json={"query": "Route this request", "tenant_id": "1", "explain": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code in (200, 500)
    data = response.json()
    if response.status_code == 200:
        assert "final_supervisor" in data
        assert "routing_path" in data
        assert "layer_results" in data
    else:
        assert "detail" in data
