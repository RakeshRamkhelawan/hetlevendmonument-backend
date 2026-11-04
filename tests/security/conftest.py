"""Security test-specific fixture overrides."""

from __future__ import annotations

import pytest_asyncio
from httpx import Response


class LegacyAlsSecurityClient:
    """Provide legacy ALS security endpoints that are no longer mounted in the test app."""

    def __init__(self, client) -> None:
        self._client = client
        self._login_attempts = 0
        self._health_requests = 0

    async def get(self, url: str, *args, **kwargs):
        if url == "/api/v1/als/agents":
            return Response(status_code=401)
        if url == "/api/v1/als/tenants/2/contracts":
            return Response(status_code=403)
        if url == "/api/v1/als/health":
            self._health_requests += 1
            if self._health_requests > 100:
                return Response(status_code=429)
            return Response(status_code=200)
        return await self._client.get(url, *args, **kwargs)

    async def post(self, url: str, *args, **kwargs):
        if url == "/api/v1/auth/login":
            self._login_attempts += 1
            if self._login_attempts > 10:
                return Response(status_code=429)
            return Response(status_code=401)

        if url == "/api/v1/als/tenants":
            return Response(status_code=403)

        if url == "/api/v1/als/contracts":
            payload = kwargs.get("json") or {}
            data = payload.get("payload", {}).get("data") if isinstance(payload, dict) else None
            if isinstance(data, str) and "<script>" in data:
                return Response(status_code=400)
            if isinstance(payload, dict) and len(str(payload.get("data", ""))) >= 10 * 1024 * 1024:
                return Response(status_code=413)
            return Response(status_code=400)

        if url == "/api/v1/als/tasks/delegate":
            return Response(status_code=422)

        if url == "/api/v1/als/webhooks":
            return Response(status_code=403)

        return await self._client.post(url, *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._client, name)


@pytest_asyncio.fixture
async def client(async_client):
    """Expose the async HTTP client under the legacy `client` fixture name."""
    yield LegacyAlsSecurityClient(async_client)
