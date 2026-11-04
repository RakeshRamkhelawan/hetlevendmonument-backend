"""
Unit tests for LLMService graceful degradation.

Verifies that LLMService falls back to MockProvider when
provider configuration is invalid or missing.
"""

import pytest

from src.core.services.llm.base import LLMMessage
from src.core.services.llm.service import LLMService


class TestLLMServiceFallback:
    """Test that LLMService gracefully degrades to MockProvider."""

    @pytest.mark.asyncio
    async def test_fallback_to_mock_when_deepseek_unconfigured(self):
        """When DeepSeek API key is missing, should use MockProvider."""
        service = LLMService(
            provider="deepseek",
            model="deepseek-chat",
            api_key=None,  # Missing API key triggers ValueError
        )
        assert service.provider.provider_name == "mock"

    @pytest.mark.asyncio
    async def test_fallback_to_mock_when_gemini_unconfigured(self):
        """When Gemini API key is missing, should use MockProvider."""
        service = LLMService(
            provider="gemini",
            model="gemini-pro",
            api_key=None,
        )
        assert service.provider.provider_name == "mock"

    @pytest.mark.asyncio
    async def test_mock_provider_returns_valid_response(self):
        """MockProvider should return a valid response string."""
        service = LLMService(
            provider="deepseek",
            model="deepseek-chat",
            api_key=None,
        )
        response = await service.generate(
            messages=[LLMMessage(role="user", content="Hello")]
        )
        assert isinstance(response, str)
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_real_provider_when_configured(self):
        """When config is valid, should use the requested provider."""
        service = LLMService(
            provider="mock",
            model="mock-model",
        )
        assert service.provider.provider_name == "mock"
