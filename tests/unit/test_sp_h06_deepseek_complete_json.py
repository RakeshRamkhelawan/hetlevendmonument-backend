"""
SP-H06: DeepSeekClient complete_json() implementatie (B-025)
"""
import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
class TestDeepSeekClientCompleteJson:

    def test_deepseek_client_has_own_complete_json_method(self) -> None:
        from src.core.llm.llm_client import DeepSeekClient
        assert "complete_json" in DeepSeekClient.__dict__, (
            "DeepSeekClient has no own complete_json() method (B-025)"
        )

    @pytest.mark.asyncio
    async def test_deepseek_complete_json_passes_response_format(self) -> None:
        from src.core.llm.llm_client import (
            DeepSeekClient, LLMConfig, LLMMessage, LLMModel, LLMProvider, LLMResponse,
        )
        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK,
            model=LLMModel.DEEPSEEK_CHAT,
            api_key="dummy",
        )
        client = DeepSeekClient(config)
        captured: dict[str, Any] = {}

        async def fake_chat(messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
            captured.update(kwargs)
            return LLMResponse(content='{}', model="deepseek-chat", provider="deepseek", success=True)

        client.chat_completion = fake_chat  # type: ignore[method-assign]
        await client.complete_json([LLMMessage(role="user", content="test")], schema=dict)

        assert "response_format" in captured, "complete_json() must pass response_format to chat_completion"
        assert captured["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_deepseek_chat_completion_includes_response_format_in_payload(self) -> None:
        from src.core.llm.llm_client import DeepSeekClient, LLMConfig, LLMMessage, LLMModel, LLMProvider

        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK,
            model=LLMModel.DEEPSEEK_CHAT,
            api_key="dummy",
        )
        client = DeepSeekClient(config)
        captured_payload: dict[str, Any] = {}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"choices": [{"message": {"content": "{}"}}], "usage": {}})

        mock_http = MagicMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        async def fake_post(url: str, json: dict[str, Any], **kw: Any) -> MagicMock:
            captured_payload.update(json)
            return mock_response

        mock_http.post = fake_post

        with patch("httpx.AsyncClient", return_value=mock_http):
            await client.chat_completion(
                [LLMMessage(role="user", content="test")],
                response_format={"type": "json_object"}
            )

        assert "response_format" in captured_payload, (
            "chat_completion() does not add response_format to HTTP payload (B-025)"
        )


@pytest.mark.unit
class TestOllamaClientCompleteJson:

    def test_ollama_complete_json_no_raise_not_implemented(self) -> None:
        from src.core.llm import llm_client
        source = inspect.getsource(llm_client)
        assert "class OllamaClient" in source
        ollama_src = source.split("class OllamaClient")[1].split("class ")[0]
        assert "raise NotImplementedError" not in ollama_src

    @pytest.mark.asyncio
    async def test_ollama_complete_json_calls_chat_completion(self) -> None:
        from src.core.llm.llm_client import LLMConfig, LLMMessage, LLMModel, LLMProvider, LLMResponse, OllamaClient

        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model=LLMModel.LLAMA3_LATEST,
            api_key="http://localhost:11434",
        )
        client = OllamaClient(config)
        call_count = 0

        async def fake_chat(messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
            nonlocal call_count
            call_count += 1
            return LLMResponse(content='{}', model="llama3:latest", provider="ollama", success=True)

        client.chat_completion = fake_chat  # type: ignore[method-assign]
        await client.complete_json([LLMMessage(role="user", content="test")], schema=dict)

        assert call_count > 0, "OllamaClient.complete_json() must call chat_completion() (B-025)"

    @pytest.mark.asyncio
    async def test_ollama_complete_json_adds_format_json(self) -> None:
        from src.core.llm.llm_client import LLMConfig, LLMMessage, LLMModel, LLMProvider, LLMResponse, OllamaClient

        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model=LLMModel.LLAMA3_LATEST,
            api_key="http://localhost:11434",
        )
        client = OllamaClient(config)
        captured: dict[str, Any] = {}

        async def fake_chat(messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
            captured.update(kwargs)
            return LLMResponse(content='{}', model="llama3:latest", provider="ollama", success=True)

        client.chat_completion = fake_chat  # type: ignore[method-assign]
        await client.complete_json([LLMMessage(role="user", content="test")], schema=dict)

        assert captured.get("format") == "json", (
            "OllamaClient.complete_json() must pass format='json' to chat_completion (B-025)"
        )
