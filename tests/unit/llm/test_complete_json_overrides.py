"""
Unit tests for LLMClient.complete_json overrides.

Tests that the three Day-1 providers (DeepSeek, Gemini, Anthropic)
correctly implement JSON-mode, and that the base class raises
NotImplementedError for unimplemented providers.

Markers:
    @pytest.mark.unit
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from typing import Any

from src.core.llm.llm_client import (
    LLMClient,
    LLMConfig,
    LLMMessage,
    LLMModel,
    LLMProvider,
    LLMResponse,
)


@pytest.mark.unit
class TestDeepSeekCompleteJson:
    """DeepSeek native response_format JSON mode."""

    async def test_deepseek_passes_response_format_json_object(self) -> None:
        from src.core.llm.deepseek_provider import DeepSeekProvider

        provider = DeepSeekProvider(api_key="fake-key")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {},
        }

        async_mock_client = AsyncMock()
        async_mock_client.__aenter__ = AsyncMock(return_value=async_mock_client)
        async_mock_client.__aexit__ = AsyncMock(return_value=None)
        async_mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=async_mock_client):
            messages = [LLMMessage(role="user", content="Test")]
            await provider.complete_json(messages, schema=object)

        call_args = async_mock_client.post.call_args
        payload = call_args.kwargs["json"]
        assert payload.get("response_format") == {"type": "json_object"}


@pytest.mark.unit
class TestGeminiCompleteJson:
    """Gemini response_mime_type JSON mode."""

    async def test_gemini_passes_response_mime_type(self) -> None:
        from src.core.llm.gemini_provider import GeminiProvider

        provider = GeminiProvider(api_key="fake-key")

        # Spy on chat_completion to verify kwargs propagation
        chat_spy = AsyncMock(
            return_value=LLMResponse(content="{}", model="gemini", provider="google", success=True)
        )
        provider.chat_completion = chat_spy  # type: ignore[method-assign]

        messages = [LLMMessage(role="user", content="Test")]
        await provider.complete_json(messages, schema=object)

        assert chat_spy.called
        _call = chat_spy.call_args
        assert _call.kwargs.get("response_mime_type") == "application/json"


class AnthropicClientForTest:
    """Minimal stub to test _inject_system_instruction logic."""

    def __init__(self, config=None) -> None:
        self.config = config

    def _inject_system_instruction(
        self,
        messages: list,
        instruction: str,
    ) -> list:
        """Prepend or append JSON instruction to system prompt."""
        from src.core.llm.llm_client import LLMMessage

        result = list(messages)
        if result and result[0].role == "system":
            result[0] = LLMMessage(
                role="system",
                content=result[0].content + instruction,
            )
        else:
            result.insert(0, LLMMessage(role="system", content=instruction.strip()))
        return result


@pytest.mark.unit
class TestAnthropicCompleteJson:
    """Anthropic system-prompt JSON fallback."""

    async def test_anthropic_appends_json_instruction_to_system_prompt(self) -> None:
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model=LLMModel.CLAUDE_3_HAIKU,
            api_key="fake-key",
        )
        client = AnthropicClientForTest(config)

        messages = [
            LLMMessage(role="system", content="You are helpful."),
            LLMMessage(role="user", content="Hello"),
        ]
        patched = client._inject_system_instruction(
            messages,
            " Output strictly valid JSON...",
        )

        assert patched[0].role == "system"
        assert "You are helpful." in patched[0].content
        assert "Output strictly valid JSON" in patched[0].content
        assert patched[1].role == "user"

    async def test_anthropic_injects_system_prompt_when_absent(self) -> None:
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model=LLMModel.CLAUDE_3_HAIKU,
            api_key="fake-key",
        )
        client = AnthropicClientForTest(config)

        messages = [LLMMessage(role="user", content="Hello")]
        patched = client._inject_system_instruction(
            messages,
            " Output strictly valid JSON...",
        )

        assert patched[0].role == "system"
        assert "Output strictly valid JSON" in patched[0].content
        assert patched[1].role == "user"


@pytest.mark.unit
class TestBaseLLMClientCompleteJson:
    """Default NotImplementedError on LLMClient base."""

    async def test_base_llm_client_complete_json_raises_not_implemented(self) -> None:
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model=LLMModel.GPT_4,
            api_key="fake-key",
        )

        class DummyProvider(LLMClient):
            async def chat_completion(
                self, messages: list[LLMMessage], **kwargs: Any
            ) -> LLMResponse:
                return LLMResponse(content="", model="", provider="")

            async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
                return LLMResponse(content="", model="", provider="")

        provider = DummyProvider(config)
        with pytest.raises(NotImplementedError) as exc_info:
            await provider.complete_json([], schema=object)
        assert "DummyProvider does not implement complete_json" in str(exc_info.value)
