"""
Integration Tests for RobustOllamaClient

Tests retry logic, fallback behavior, and health checks
without requiring actual Ollama running (uses mock aiohttp).
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from src.core.llm.ollama_client import RobustOllamaClient, OllamaConnectionError


@pytest.fixture
def client():
    """Create test client pointing to local mock server."""
    return RobustOllamaClient(
        base_url="http://localhost:11434",
        timeout_secs=5,
        max_retries=2,
        preferred_models=["nomic-embed-text"],
    )


@pytest.mark.asyncio
async def test_initialization_success():
    """Test successful initialization with model discovery."""
    client = RobustOllamaClient()

    with patch("aiohttp.ClientSession.get") as mock_get:
        # Mock successful health check
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                "models": [
                    {"name": "nomic-embed-text:latest"},
                    {"name": "llama2:latest"},
                ]
            }
        )
        mock_get.return_value.__aenter__.return_value = mock_resp

        with patch("aiohttp.ClientSession.post"):
            result = await client.initialize()
            assert result is True
            assert len(client.available_models) == 2
            assert "nomic-embed-text:latest" in client.available_models


@pytest.mark.asyncio
async def test_initialization_failure_connection():
    """Test initialization failure on connection error."""
    client = RobustOllamaClient()

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.side_effect = ConnectionError("Connection refused")

        result = await client.initialize()
        assert result is False
        assert client.initialized is False


@pytest.mark.asyncio
async def test_embed_with_retry():
    """Test embedding with automatic retry on transient failure."""
    client = RobustOllamaClient(max_retries=3)
    await client.initialize()

    with patch("aiohttp.ClientSession.post") as mock_post:
        # First call fails, second succeeds
        mock_resp_fail = AsyncMock()
        mock_resp_fail.status = 500
        mock_resp_fail.text = AsyncMock(return_value="Internal error")

        mock_resp_success = AsyncMock()
        mock_resp_success.status = 200
        mock_resp_success.json = AsyncMock(return_value={"embedding": [0.1, 0.2, 0.3]})

        mock_post.return_value.__aenter__.side_effect = [
            mock_resp_fail,  # First attempt fails
            mock_resp_success,  # Second attempt succeeds
        ]

        result = await client.embed("test text")

        assert result["success"] is True
        assert result["embedding"] == [0.1, 0.2, 0.3]
        assert mock_post.call_count == 2  # Called twice due to retry


@pytest.mark.asyncio
async def test_embed_max_retries_exceeded():
    """Test embedding fails gracefully after max retries."""
    client = RobustOllamaClient(max_retries=2)

    with patch("aiohttp.ClientSession.post") as mock_post:
        # All calls fail
        mock_resp = AsyncMock()
        mock_resp.status = 503
        mock_resp.text = AsyncMock(return_value="Service unavailable")
        mock_post.return_value.__aenter__.return_value = mock_resp

        result = await client.embed("test text")

        assert result["success"] is False
        assert "error" in result
        # Should retry max_retries times
        assert mock_post.call_count >= client.max_retries


@pytest.mark.asyncio
async def test_health_check_healthy():
    """Test health check returns healthy status."""
    client = RobustOllamaClient()

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"models": [{"name": "nomic-embed-text:latest"}]})
        mock_get.return_value.__aenter__.return_value = mock_resp

        result = await client.health_check()

        assert result["healthy"] is True
        assert result["model_count"] == 1


@pytest.mark.asyncio
async def test_health_check_unhealthy():
    """Test health check returns unhealthy status."""
    client = RobustOllamaClient()

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 503
        mock_get.return_value.__aenter__.return_value = mock_resp

        result = await client.health_check()

        assert result["healthy"] is False
        assert "error" in result


@pytest.mark.asyncio
async def test_health_check_connection_error():
    """Test health check handles connection errors."""
    client = RobustOllamaClient()

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.side_effect = ConnectionError("Cannot connect")

        result = await client.health_check()

        assert result["healthy"] is False
        # health_check geeft str(e) door; toets dat de fouttekst van de exception
        # daadwerkelijk bij de aanroeper aankomt. Zocht eerder op "Connection", wat niet
        # voorkomt in de eigen mock-boodschap "Cannot connect" -- de test was rood.
        assert "Cannot connect" in result.get("error", "")


@pytest.mark.asyncio
async def test_chat_with_messages():
    """Test chat completion with message history."""
    client = RobustOllamaClient()

    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                "message": {"content": "Response text"},
                "model": "llama2:latest",
                "prompt_eval_count": 10,
                "eval_count": 50,
            }
        )
        mock_post.return_value.__aenter__.return_value = mock_resp

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]

        result = await client.chat(messages)

        assert result["success"] is True
        assert result["content"] == "Response text"
        assert result["tokens"]["prompt"] == 10
        assert result["tokens"]["completion"] == 50


@pytest.mark.asyncio
async def test_context_manager():
    """Test async context manager usage."""
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"models": []})
        mock_get.return_value.__aenter__.return_value = mock_resp

        async with RobustOllamaClient() as client:
            assert client.session is not None


@pytest.mark.asyncio
async def test_empty_embedding():
    """Test embedding with empty text returns zero vector."""
    client = RobustOllamaClient()

    result = await client.embed("")

    assert result["success"] is True
    assert result["embedding"] == []


@pytest.mark.asyncio
async def test_url_detection():
    """Test automatic URL detection for container vs host."""
    # Test with env var set
    import os

    os.environ["OLLAMA_BASE_URL"] = "http://custom:11434"
    client = RobustOllamaClient()
    assert client.base_url == "http://custom:11434"

    # Test fallback to container DNS
    del os.environ["OLLAMA_BASE_URL"]
    client = RobustOllamaClient()
    assert "ollama" in client.base_url or "localhost" in client.base_url


@pytest.mark.asyncio
async def test_exponential_backoff():
    """Test that retries use exponential backoff."""
    import time

    client = RobustOllamaClient(
        max_retries=3,
        retry_backoff_max=1,  # Cap at 1s for test
    )

    with patch("aiohttp.ClientSession.post") as mock_post:
        # All calls timeout
        mock_post.side_effect = asyncio.TimeoutError("Timeout")

        start = time.time()
        result = await client.embed("test")
        elapsed = time.time() - start

        # Should have delays between retries (at least some backoff)
        # This is approximate since timing varies
        assert result["success"] is False
        assert elapsed > 0.1  # Some delay expected from backoff


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
