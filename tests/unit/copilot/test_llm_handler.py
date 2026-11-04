"""
Unit tests for LLMHandler.

Test taxonomy per CLAUDE.md kwaliteitsloop:
    - Happy paths      (valid JSON parse)
    - Unhappy paths    (retry failure, provider exception)
    - Edge cases       (empty context)

Markers:
    @pytest.mark.unit
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.core.copilot.llm_handler import LLMHandler
from src.core.copilot.schemas import CopilotAction
from src.core.llm.llm_client import (
    LLMClient,
    LLMConfig,
    LLMMessage,
    LLMModel,
    LLMProvider,
    LLMResponse,
)


class MockProvider(LLMClient):
    """Minimal provider for unit testing."""

    def __init__(self) -> None:
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model=LLMModel.GPT_4,
            api_key="fake",
        )
        super().__init__(config)

    async def chat_completion(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        return LLMResponse(content="", model="", provider="")

    async def text_completion(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return LLMResponse(content="", model="", provider="")


@pytest.mark.unit
class TestLLMHandlerGetAction:
    """JSON-mode call and retry behaviour."""

    async def test_get_action_returns_parsed_copilot_action_on_valid_json(
        self,
    ) -> None:
        provider = MockProvider()
        valid_json = json.dumps(
            {
                "message": "Hello user",
                "action": "navigate",
                "action_params": {"page": "home"},
                "confidence": 0.95,
                "reasoning": "User asked for home",
            }
        )
        provider.complete_json = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResponse(
                content=valid_json,
                model="gpt-4",
                provider="openai",
                success=True,
            )
        )

        handler = LLMHandler(provider)
        action = await handler.get_action("Go home", {})

        assert isinstance(action, CopilotAction)
        assert action.message == "Hello user"
        assert action.action == "navigate"
        assert provider.complete_json.call_count == 1

    async def test_get_action_retries_once_on_validation_error(self) -> None:
        provider = MockProvider()
        bad_json = "not json"
        good_json = json.dumps(
            {
                "message": "Hello user",
                "action": None,
                "action_params": {},
                "confidence": 0.9,
                "reasoning": "Test",
            }
        )
        provider.complete_json = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                LLMResponse(content=bad_json, model="m", provider="p", success=True),
                LLMResponse(content=good_json, model="m", provider="p", success=True),
            ]
        )

        handler = LLMHandler(provider)
        action = await handler.get_action("Test", {})

        assert isinstance(action, CopilotAction)
        assert provider.complete_json.call_count == 2
        # Verify retry prompt contains correction instruction
        second_call = provider.complete_json.call_args_list[1]
        messages = second_call.kwargs["messages"]
        assert any("invalid JSON" in m.content for m in messages)

    async def test_get_action_raises_after_two_validation_errors(self) -> None:
        provider = MockProvider()
        provider.complete_json = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResponse(
                content="bad json",
                model="m",
                provider="p",
                success=True,
            )
        )

        handler = LLMHandler(provider)
        with pytest.raises(ValidationError):
            await handler.get_action("Test", {})

        assert provider.complete_json.call_count == 2

    async def test_get_action_raises_on_provider_exception(self) -> None:
        provider = MockProvider()
        provider.complete_json = AsyncMock(  # type: ignore[method-assign]
            side_effect=ConnectionError("LLM down")
        )

        handler = LLMHandler(provider)
        with pytest.raises(ConnectionError):
            await handler.get_action("Test", {})


@pytest.mark.unit
class TestLLMHandlerSystemPrompt:
    """System prompt construction."""

    async def test_system_prompt_includes_language(self) -> None:
        provider = MockProvider()
        provider.complete_json = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "message": "Hoi",
                        "action": None,
                        "action_params": {},
                        "confidence": 0.5,
                        "reasoning": "Test",
                    }
                ),
                model="m",
                provider="p",
                success=True,
            )
        )

        handler = LLMHandler(provider)
        await handler.get_action("Test", {}, language="nl")

        messages = provider.complete_json.call_args.kwargs["messages"]
        system_msg = messages[0]
        assert "Language: nl" in system_msg.content

    async def test_system_prompt_includes_context_snapshot_keys(self) -> None:
        provider = MockProvider()
        provider.complete_json = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "message": "Hoi",
                        "action": None,
                        "action_params": {},
                        "confidence": 0.5,
                        "reasoning": "Test",
                    }
                ),
                model="m",
                provider="p",
                success=True,
            )
        )

        handler = LLMHandler(provider)
        await handler.get_action("Test", {"page": "home", "user_role": "admin"})

        messages = provider.complete_json.call_args.kwargs["messages"]
        system_msg = messages[0]
        # Security fix: context keys are no longer interpolated raw;
        # only the count is mentioned to avoid prompt injection.
        assert "2 context item(s) are available" in system_msg.content


@pytest.mark.unit
class TestLLMHandlerProperties:
    """Property accessors."""

    def test_handler_captures_model_id_and_version(self) -> None:
        provider = MockProvider()
        handler = LLMHandler(provider, model_id="gemini-pro", model_version="v1.0")
        assert handler.model_id == "gemini-pro"
        assert handler.model_version == "v1.0"


@pytest.mark.unit
class TestCritical3CapabilityCatalog:
    """CRITICAL-3: system prompt must include platform capability catalog."""

    async def test_system_prompt_includes_capability_catalog(self) -> None:
        """When capabilities are provided, system prompt must list them."""
        provider = MockProvider()
        provider.complete_json = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "message": "OK",
                        "action": None,
                        "action_params": {},
                        "confidence": 0.5,
                        "reasoning": "Test",
                    }
                ),
                model="m",
                provider="p",
                success=True,
            )
        )

        handler = LLMHandler(provider)
        capabilities = {
            "tools": [
                {"name": "navigate", "description": "Navigate to a page"},
                {"name": "search", "description": "Search knowledge base"},
            ]
        }
        await handler.get_action("Test", {}, language="en", capabilities=capabilities)

        messages = provider.complete_json.call_args.kwargs["messages"]
        system_msg = messages[0]
        assert "=== AVAILABLE TOOLS ===" in system_msg.content
        assert "navigate" in system_msg.content
        assert "search" in system_msg.content


@pytest.mark.unit
class TestHigh4RetrievalParameter:
    """HIGH-4: get_action() must accept retrieval_results parameter."""

    async def test_get_action_accepts_retrieval_results(self) -> None:
        """When retrieval_results are provided, they appear in system prompt."""
        provider = MockProvider()
        provider.complete_json = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "message": "OK",
                        "action": None,
                        "action_params": {},
                        "confidence": 0.5,
                        "reasoning": "Test",
                    }
                ),
                model="m",
                provider="p",
                success=True,
            )
        )

        handler = LLMHandler(provider)
        retrieval = [{"title": "Doc 1", "content": "Important info"}]
        await handler.get_action("Test", {}, language="en", retrieval_results=retrieval)

        messages = provider.complete_json.call_args.kwargs["messages"]
        system_msg = messages[0]
        assert "=== RETRIEVED CONTEXT ===" in system_msg.content
        assert "Doc 1" in system_msg.content

    async def test_get_action_backward_compat_no_retrieval(self) -> None:
        """Calling without retrieval_results must still work."""
        provider = MockProvider()
        provider.complete_json = AsyncMock(  # type: ignore[method-assign]
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "message": "OK",
                        "action": None,
                        "action_params": {},
                        "confidence": 0.5,
                        "reasoning": "Test",
                    }
                ),
                model="m",
                provider="p",
                success=True,
            )
        )

        handler = LLMHandler(provider)
        action = await handler.get_action("Test", {})
        assert isinstance(action, CopilotAction)
        assert action.message == "OK"
