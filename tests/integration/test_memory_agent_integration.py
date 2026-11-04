"""Integration tests for memory domain wiring."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_memory_router_is_registered(integration_client: AsyncClient):
    """The agent-memory endpoints should be reachable (not 404)."""
    response = await integration_client.get("/api/v1/agent-memory/stats")
    assert (
        response.status_code != 404
    ), "Memory router not registered — check router_registry.py:269-276 try/except"


@pytest.mark.asyncio
async def test_memory_boot_context_endpoint_exists(integration_client: AsyncClient):
    """The boot-context endpoint should be reachable."""
    response = await integration_client.get("/api/v1/agent-memory/boot-context/test-agent")
    assert response.status_code != 404
