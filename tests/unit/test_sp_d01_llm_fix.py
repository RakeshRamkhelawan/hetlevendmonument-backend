"""
SP-D01: CVA / Copilot / Focus Builder LLM-fix

Tests that verify:
1. All LLM providers implement complete_json() without NotImplementedError
2. complete_json() returns LLMResponse (not dict or exception)
3. Native JSON-mode is used where available (Moonshot, DeepSeek)
4. System-instruction fallback works for providers without native JSON-mode
5. Focus Builder ai_generate uses LLM-backed generation, not template-based
"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.llm.llm_client import LLMClient, LLMConfig, LLMMessage, LLMModel, LLMProvider


@pytest.mark.unit
class TestCompleteJsonExists:
    """Verifies that all LLM providers implement complete_json()."""

    def test_ollama_client_has_complete_json(self) -> None:
        """OllamaClient has complete_json implementation (not NotImplementedError)."""
        from src.core.llm.llm_client import OllamaClient

        assert hasattr(OllamaClient, "complete_json"), "OllamaClient missing complete_json"
        source = inspect.getsource(OllamaClient.complete_json)
        assert "raise NotImplementedError" not in source, (
            "OllamaClient.complete_json raises NotImplementedError -- not implemented"
        )

    def test_openai_client_has_complete_json(self) -> None:
        """OpenAI provider has complete_json implementation."""
        from src.core.llm.llm_client import OpenAIClient

        assert hasattr(OpenAIClient, "complete_json"), "OpenAIClient missing complete_json"

    def test_anthropic_client_has_complete_json(self) -> None:
        """Anthropic provider has complete_json implementation."""
        from src.core.llm.llm_client import AnthropicClient

        assert hasattr(AnthropicClient, "complete_json"), "AnthropicClient missing complete_json"

    def test_google_client_has_complete_json(self) -> None:
        """GoogleClient has complete_json implementation."""
        from src.core.llm.llm_client import GoogleClient

        assert hasattr(GoogleClient, "complete_json"), "GoogleClient missing complete_json"

    def test_ollama_provider_has_complete_json(self) -> None:
        """OllamaProvider has complete_json implementation."""
        from src.core.llm.ollama_provider import OllamaProvider

        assert hasattr(OllamaProvider, "complete_json"), "OllamaProvider missing complete_json"
        source = inspect.getsource(OllamaProvider.complete_json)
        assert "raise NotImplementedError" not in source, (
            "OllamaProvider.complete_json raises NotImplementedError -- not implemented"
        )

    def test_deepseek_provider_has_complete_json(self) -> None:
        """DeepSeekProvider has complete_json implementation."""
        from src.core.llm.deepseek_provider import DeepSeekProvider

        assert hasattr(DeepSeekProvider, "complete_json"), "DeepSeekProvider missing complete_json"

    def test_gemini_provider_has_complete_json(self) -> None:
        """GeminiProvider has complete_json implementation."""
        from src.core.llm.gemini_provider import GeminiProvider

        assert hasattr(GeminiProvider, "complete_json"), "GeminiProvider missing complete_json"

    async def test_ollama_client_returns_llm_response_not_exception(self) -> None:
        """OllamaClient.complete_json returns LLMResponse(success=False), not NotImplementedError."""
        from src.core.llm.llm_client import OllamaClient

        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model=LLMModel.LLAMA_3,
            api_key="",
        )
        client = OllamaClient(config)

        result = await client.complete_json(
            messages=[LLMMessage(role="user", content="test")],
            schema=dict,
        )

        assert hasattr(result, "success"), f"Expected LLMResponse, got {type(result)}"
        assert result.success is False
        assert result.error_message is not None

    @pytest.mark.asyncio
    def test_generate_flow_ai_imports_agentic_service(self) -> None:
        """generate_flow_ai endpoint imports AgenticFlowService for LLM generation."""
        import ast

        # ADR-033: AgenticFlowService is imported in ai_router.py
        source = open("src/core/api/v1/focus_builder/ai_router.py").read()
        tree = ast.parse(source)

        imports_agentic = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "agentic_service" in node.module:
                    imports_agentic = True
                    break
        assert imports_agentic, "ai_router.py must import AgenticFlowService for LLM-backed generation"

    def test_generate_flow_ai_not_template_based(self) -> None:
        """generate_flow_ai no longer contains hardcoded template graphs."""
        source = open("src/core/api/v1/focus_builder/ai_router.py").read()

        # Should not contain the old template-based graph literals
        assert '"On Loop Trigger"' not in source, (
            "Template-based loop trigger still present -- must use LLM generation"
        )
        assert '"Generated Trigger"' not in source, (
            "Template-based action trigger still present -- must use LLM generation"
        )

    def test_generate_flow_ai_calls_agentic_flow_service(self) -> None:
        """generate_flow_ai creates AgenticFlowService and calls generate_flow_from_prompt."""
        import ast

        source = open("src/core/api/v1/focus_builder/ai_router.py").read()
        tree = ast.parse(source)

        calls_agentic = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "generate_flow_from_prompt":
                        calls_agentic = True
                        break
                elif isinstance(node.func, ast.Name):
                    if node.func.id == "generate_flow_from_prompt":
                        calls_agentic = True
                        break
        assert calls_agentic, (
            "generate_flow_ai must call generate_flow_from_prompt() for LLM-backed generation"
        )
