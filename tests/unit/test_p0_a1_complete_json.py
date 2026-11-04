"""
AUDIT-P0-A1: complete_json() missing in OllamaProvider, MockProvider, GoogleClient.

RED PHASE OUTPUT (2026-05-28):
  OllamaProvider: NotImplementedError: OllamaProvider does not implement complete_json.
    Use a provider with native JSON-mode (DeepSeek, Gemini, Anthropic).
  MockProvider: AttributeError: 'MockProvider' object has no attribute 'complete_json'
  GoogleClient: NotImplementedError: GoogleClient does not implement complete_json.
    Use a provider with native JSON-mode (DeepSeek, Gemini, Anthropic).
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

TEST_GOOGLE_KEY = "unit-test-fixture-key"  # nosec B105 - unit test fixture only


def _make_ollama_session_mock(status: int = 200, content: str = '{"result": "ok"}') -> MagicMock:
    """Build a mock aiohttp session that returns the given JSON content."""
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.json = AsyncMock(
        return_value={"message": {"content": content}, "model": "test-model:latest"}
    )
    mock_response.text = AsyncMock(return_value=f"HTTP {status} error")

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_cm)
    return mock_session


@pytest.mark.unit
class TestOllamaProviderCompleteJson:
    """OllamaProvider.complete_json(): JSON-mode via format=json parameter."""

    @pytest.mark.asyncio
    async def test_complete_json_returns_valid_response_on_success(self):
        """Happy path: successful JSON response returns LLMResponse with success=True."""
        from src.core.llm.llm_client import LLMMessage
        from src.core.llm.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        provider.initialized = True
        provider.available_models = ["llama3.1:8b"]
        provider.session = _make_ollama_session_mock(
            status=200, content='{"action": "navigate", "confidence": 0.9}'
        )

        messages = [LLMMessage(role="user", content="What should I do?")]
        result = await provider.complete_json(messages, schema=dict)

        assert result.success is True
        assert result.content is not None
        assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_complete_json_returns_failure_on_api_error(self):
        """Unhappy path: API error returns LLMResponse with success=False."""
        from src.core.llm.llm_client import LLMMessage
        from src.core.llm.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        provider.initialized = True
        provider.available_models = ["llama3.1:8b"]

        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_cm)
        provider.session = mock_session

        messages = [LLMMessage(role="user", content="What should I do?")]
        result = await provider.complete_json(messages, schema=dict)

        assert result.success is False
        assert result.error_message is not None

    @pytest.mark.asyncio
    async def test_complete_json_strips_code_fences(self):
        """
        Ollama models sometimes wrap JSON in markdown code fences.
        complete_json() must strip them so callers can parse the content.
        """
        from src.core.llm.llm_client import LLMMessage
        from src.core.llm.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        provider.initialized = True
        provider.available_models = ["llama3.1:8b"]
        fenced_content = '```json\n{"action": "navigate", "confidence": 0.9}\n```'
        provider.session = _make_ollama_session_mock(status=200, content=fenced_content)

        messages = [LLMMessage(role="user", content="What should I do?")]
        result = await provider.complete_json(messages, schema=dict)

        assert result.success is True
        assert "```" not in result.content
        assert result.content.strip().startswith("{")


@pytest.mark.unit
class TestMockProviderCompleteJson:
    """MockProvider.complete_json(): deterministic test double with configurable failure."""

    @pytest.mark.asyncio
    async def test_complete_json_returns_dict_on_success(self):
        """Happy path: MockProvider returns a successful response."""
        from src.core.llm.llm_client import LLMMessage
        from src.core.llm.mock_provider import MockProvider

        provider = MockProvider()
        messages = [LLMMessage(role="user", content="What should I do?")]
        result = await provider.complete_json(messages, schema=dict)

        assert result is not None
        assert result.success is True

    @pytest.mark.asyncio
    async def test_complete_json_raises_on_configured_failure(self):
        """
        Security / test harness: when _should_fail=True, complete_json raises RuntimeError.
        This allows tests to simulate LLM failures without a real API.
        """
        from src.core.llm.llm_client import LLMMessage
        from src.core.llm.mock_provider import MockProvider

        provider = MockProvider()
        provider._should_fail = True
        messages = [LLMMessage(role="user", content="What should I do?")]

        with pytest.raises(RuntimeError, match="MockProvider configured to fail"):
            await provider.complete_json(messages, schema=dict)


@pytest.mark.unit
class TestGoogleClientCompleteJson:
    """GoogleClient.complete_json(): JSON instruction injection via system message."""

    @pytest.mark.asyncio
    async def test_complete_json_returns_success_response(self):
        """Happy path: GoogleClient.complete_json() wraps chat_completion() with JSON hint."""
        from src.core.llm.llm_client import (
            GoogleClient,
            LLMConfig,
            LLMMessage,
            LLMModel,
            LLMProvider,
            LLMResponse,
        )

        config = LLMConfig(
            provider=LLMProvider.GOOGLE,
            model=LLMModel.GEMINI_1_5_FLASH,
            api_key=TEST_GOOGLE_KEY,
        )
        client = GoogleClient(config)
        client._available = True

        expected_response = LLMResponse(
            content='{"result": "ok", "confidence": 1.0}',
            model=LLMModel.GEMINI_1_5_FLASH.value,
            provider=LLMProvider.GOOGLE.value,
            success=True,
        )
        client.chat_completion = AsyncMock(return_value=expected_response)

        messages = [LLMMessage(role="user", content="Classify this intent.")]
        result = await client.complete_json(messages, schema=dict)

        assert result.success is True
        assert result.content == '{"result": "ok", "confidence": 1.0}'

    @pytest.mark.asyncio
    async def test_complete_json_returns_failure_on_llm_error(self):
        """Unhappy path: when chat_completion() fails, complete_json() propagates failure."""
        from src.core.llm.llm_client import (
            GoogleClient,
            LLMConfig,
            LLMMessage,
            LLMModel,
            LLMProvider,
            LLMResponse,
        )

        config = LLMConfig(
            provider=LLMProvider.GOOGLE,
            model=LLMModel.GEMINI_1_5_FLASH,
            api_key=TEST_GOOGLE_KEY,
        )
        client = GoogleClient(config)
        client._available = True

        failure_response = LLMResponse(
            content="",
            model=LLMModel.GEMINI_1_5_FLASH.value,
            provider=LLMProvider.GOOGLE.value,
            success=False,
            error_message="Google API quota exceeded",
        )
        client.chat_completion = AsyncMock(return_value=failure_response)

        messages = [LLMMessage(role="user", content="Classify this intent.")]
        result = await client.complete_json(messages, schema=dict)

        assert result.success is False
        assert result.error_message is not None


@pytest.mark.unit
class TestCompleteJsonBehavioral:
    """Behavioral: verify model source and contract-level properties."""

    @pytest.mark.asyncio
    async def test_complete_json_uses_configured_model_not_hardcoded(self):
        """
        Behavioral: the model name in the LLMResponse comes from available_models
        (OllamaProvider), never from a hardcoded literal.
        """
        from src.core.llm.llm_client import LLMMessage
        from src.core.llm.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        provider.initialized = True
        provider.available_models = ["custom-model:7b"]

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "message": {"content": '{"ok": true}'},
                "model": "custom-model:7b",
            }
        )
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_cm)
        provider.session = mock_session

        messages = [LLMMessage(role="user", content="Test.")]
        result = await provider.complete_json(messages, schema=dict)

        assert result.success is True
        assert result.model == "custom-model:7b", (
            "Model name must come from available_models, not a hardcoded literal"
        )

    @pytest.mark.asyncio
    async def test_complete_json_passes_format_json_to_ollama_api(self):
        """
        Behavioral: OllamaProvider.complete_json() must include format='json' in
        the request payload sent to the Ollama API.
        """
        from src.core.llm.llm_client import LLMMessage
        from src.core.llm.ollama_provider import OllamaProvider

        provider = OllamaProvider()
        provider.initialized = True
        provider.available_models = ["llama3.1:8b"]

        captured_payload: dict[str, Any] = {}

        def _capture_post(url: str, json: dict[str, Any], **kwargs: Any) -> Any:
            # Must be a regular function — session.post() returns an async CM, not a coroutine
            captured_payload.update(json)
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={"message": {"content": "{}"}, "model": "llama3.1:8b"}
            )
            mock_cm = MagicMock()
            mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_cm.__aexit__ = AsyncMock(return_value=None)
            return mock_cm

        mock_session = MagicMock()
        mock_session.post = _capture_post
        provider.session = mock_session

        messages = [LLMMessage(role="user", content="Test.")]
        await provider.complete_json(messages, schema=dict)

        assert captured_payload.get("format") == "json", (
            "complete_json() must include format='json' in the Ollama API payload"
        )
