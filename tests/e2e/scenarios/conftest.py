"""
E2E Scenarios Test Configuration

Provides fixtures for contract workflow and scenario tests.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest_asyncio.fixture
async def async_client():
    """Create async test client using ASGI transport."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def infrastructure(async_client: AsyncClient):
    """
    Provide test infrastructure for contract workflow tests.

    Returns a dictionary with:
    - client: HTTP async client
    - tenant_id: Default test tenant ID
    - base_url: Base URL for API calls
    """
    return {
        "client": async_client,
        "chief": async_client,  # Alias for compatibility
        "tenant_id": 1,
        "base_url": "http://test",
    }
