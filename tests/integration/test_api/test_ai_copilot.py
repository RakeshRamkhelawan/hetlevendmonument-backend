"""AI Copilot integration tests — uses async_client fixture (not TestClient(app))."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_suggest_tools_streaming(async_client, admin_token):
    """Test the streaming endpoint for AI Copilot."""

    async def mock_stream(prompt, **kwargs):
        yield {"text": "Hello"}
        yield {"text": " World"}

    with patch("src.core.api.v1.ai_copilot.router.TenantTaalmodel") as mock_get_provider:
        provider = mock_get_provider.return_value
        provider.stream_response = mock_stream

        response = await async_client.post(
            "/api/v1/ai-copilot/suggest-tools",
            json={"query": "Help me search docs"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        content = response.text

        assert "event: reasoning" in content
        assert "event: text" in content
        assert '{"token": "Hello"}' in content
        assert '{"token": " World"}' in content
