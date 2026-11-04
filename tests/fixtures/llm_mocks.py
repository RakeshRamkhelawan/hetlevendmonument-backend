"""
tests/fixtures/llm_mocks.py - LLM Provider Mocks

Provides deterministic, configurable mocks for LLM providers (Gemini, Ollama, etc.)
All mocks support async/await and are thread-safe.

KEY PRINCIPLES:
1. Deterministic responses (no randomness)
2. Configurable for edge cases
3. Async/await compatible
4. Type-safe with full annotations

Created: 2025-12-11
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from unittest.mock import AsyncMock, MagicMock

import pytest

# ============================================================================
# FAKE LLM PROVIDER (Base Class)
# ============================================================================


@dataclass
class LLMResponse:
    """Structured LLM response object."""

    text: str
    tokens_used: int = 0
    model: str = "mock-model"
    finish_reason: str = "stop"
    metadata: Dict[str, Any] = field(default_factory=dict)


class FakeLLMProvider:
    """
    Deterministic LLM provider for testing.

    Returns pre-configured responses in order. Cycles through responses
    if more requests are made than responses configured.

    Example:
        >>> llm = FakeLLMProvider(responses={
        ...     "What is AI?": "AI is artificial intelligence.",
        ...     "default": "I don't know.",
        ... })
        >>> response = await llm.generate("What is AI?")
        >>> assert response.text == "AI is artificial intelligence."
        >>> response = await llm.generate("Unknown question")
        >>> assert response.text == "I don't know."
    """

    def __init__(
        self,
        responses: Optional[Dict[str, str]] = None,
        default_response: str = "Mock LLM response",
        model_name: str = "mock-model",
        should_fail: bool = False,
        failure_message: str = "LLM request failed",
    ):
        """
        Initialize FakeLLMProvider.

        Args:
            responses: Dict mapping prompts to responses
            default_response: Fallback response if prompt not in responses
            model_name: Model name to return in metadata
            should_fail: If True, raise exception on generate()
            failure_message: Error message to raise if should_fail=True
        """
        self.responses = responses or {}
        self.default_response = default_response
        self.model_name = model_name
        self.should_fail = should_fail
        self.failure_message = failure_message

        # Tracking
        self.call_log: List[Dict[str, Any]] = []
        self.call_count = 0

    async def generate(
        self, prompt: str, max_tokens: int = 1024, temperature: float = 0.7, **kwargs
    ) -> LLMResponse:
        """
        Generate response from prompt.

        Args:
            prompt: Input prompt
            max_tokens: Max tokens to generate (ignored in mock)
            temperature: Sampling temperature (ignored in mock)
            **kwargs: Additional model parameters (logged but ignored)

        Returns:
            LLMResponse with text and metadata

        Raises:
            Exception: If should_fail=True
        """
        self.call_count += 1
        self.call_log.append(
            {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "kwargs": kwargs,
            }
        )

        if self.should_fail:
            raise Exception(self.failure_message)

        # Find response (exact match or default)
        response_text = self.responses.get(prompt, self.default_response)

        return LLMResponse(
            text=response_text,
            tokens_used=len(response_text.split()),  # Naive token count
            model=self.model_name,
            finish_reason="stop",
            metadata={"call_count": self.call_count},
        )

    def set_response(self, prompt: str, response: str):
        """Add or update a response mapping."""
        self.responses[prompt] = response

    def clear_responses(self):
        """Clear all response mappings."""
        self.responses.clear()

    def reset(self):
        """Reset call log and counters."""
        self.call_log.clear()
        self.call_count = 0


# ============================================================================
# GEMINI MOCK
# ============================================================================


class MockGeminiClient:
    """
    Mock Google Gemini API client.

    Matches Gemini API interface with configurable responses.

    Example:
        >>> client = MockGeminiClient()
        >>> client.set_responses(["Response 1", "Response 2"])
        >>> result = await client.generate_content("Test prompt")
        >>> assert result.text == "Response 1"
        >>> result = await client.generate_content("Another prompt")
        >>> assert result.text == "Response 2"
    """

    def __init__(
        self,
        responses: Optional[List[str]] = None,
        model_name: str = "gemini-pro",
        should_fail: bool = False,
    ):
        """
        Initialize MockGeminiClient.

        Args:
            responses: List of responses to cycle through
            model_name: Model identifier
            should_fail: If True, raise errors on API calls
        """
        self.responses = responses or ["Mock Gemini response"]
        self.response_index = 0
        self.model_name = model_name
        self.should_fail = should_fail

        self.call_log: List[Dict[str, Any]] = []

    async def generate_content(
        self,
        prompt: Union[str, List[str]],
        generation_config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> MagicMock:
        """
        Generate content (mock Gemini API).

        Returns a MagicMock that mimics Gemini response structure:
        - response.text: The generated text
        - response.candidates[0].content.parts[0].text: Nested text access
        """
        if isinstance(prompt, list):
            prompt = " ".join(prompt)

        self.call_log.append(
            {
                "prompt": prompt,
                "generation_config": generation_config,
                "kwargs": kwargs,
            }
        )

        if self.should_fail:
            raise Exception("Gemini API error (mock)")

        # Get next response (cycle through list)
        response_text = self.responses[self.response_index % len(self.responses)]
        self.response_index += 1

        # Create mock response matching Gemini structure
        mock_response = MagicMock()
        mock_response.text = response_text

        # Nested structure for Gemini API compatibility
        mock_part = MagicMock()
        mock_part.text = response_text

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content
        mock_candidate.finish_reason = "STOP"

        mock_response.candidates = [mock_candidate]
        mock_response.prompt_feedback = None

        return mock_response

    def set_responses(self, responses: List[str]):
        """Update response list and reset index."""
        self.responses = responses
        self.response_index = 0

    def set_fail_mode(self, should_fail: bool):
        """Enable/disable failure mode."""
        self.should_fail = should_fail

    def reset(self):
        """Reset state."""
        self.response_index = 0
        self.call_log.clear()


# ============================================================================
# OLLAMA MOCK
# ============================================================================


class MockOllamaClient:
    """
    Mock Ollama API client.

    Supports both sync and async interfaces for Ollama.

    Example:
        >>> client = MockOllamaClient()
        >>> response = await client.chat(model="llama2", messages=[...])
        >>> assert response["message"]["content"] == "Mock Ollama response"
    """

    def __init__(
        self,
        responses: Optional[List[str]] = None,
        model_name: str = "llama2",
        should_fail: bool = False,
    ):
        """
        Initialize MockOllamaClient.

        Args:
            responses: List of responses to return
            model_name: Default model name
            should_fail: If True, raise errors
        """
        self.responses = responses or ["Mock Ollama response"]
        self.response_index = 0
        self.model_name = model_name
        self.should_fail = should_fail

        self.call_log: List[Dict[str, Any]] = []

    async def chat(
        self, model: str, messages: List[Dict[str, str]], stream: bool = False, **kwargs
    ) -> Dict[str, Any]:
        """
        Chat completion (Ollama chat API).

        Args:
            model: Model name (e.g., "llama2")
            messages: List of message dicts with role and content
            stream: If True, would stream tokens (mock ignores this)
            **kwargs: Additional parameters

        Returns:
            Dict with Ollama response format
        """
        self.call_log.append(
            {
                "method": "chat",
                "model": model,
                "messages": messages,
                "stream": stream,
                "kwargs": kwargs,
            }
        )

        if self.should_fail:
            raise Exception("Ollama API error (mock)")

        response_text = self.responses[self.response_index % len(self.responses)]
        self.response_index += 1

        return {
            "model": model,
            "created_at": "2025-12-11T00:00:00Z",
            "message": {
                "role": "assistant",
                "content": response_text,
            },
            "done": True,
            "total_duration": 1000000000,  # nanoseconds
            "load_duration": 100000000,
            "prompt_eval_count": 50,
            "eval_count": 100,
        }

    async def generate(
        self, model: str, prompt: str, stream: bool = False, **kwargs
    ) -> Dict[str, Any]:
        """
        Generate completion (Ollama generate API).

        Simpler interface than chat(), takes raw prompt string.
        """
        self.call_log.append(
            {
                "method": "generate",
                "model": model,
                "prompt": prompt,
                "stream": stream,
                "kwargs": kwargs,
            }
        )

        if self.should_fail:
            raise Exception("Ollama API error (mock)")

        response_text = self.responses[self.response_index % len(self.responses)]
        self.response_index += 1

        return {
            "model": model,
            "created_at": "2025-12-11T00:00:00Z",
            "response": response_text,
            "done": True,
        }

    def set_responses(self, responses: List[str]):
        """Update response list."""
        self.responses = responses
        self.response_index = 0

    def set_fail_mode(self, should_fail: bool):
        """Enable/disable failure mode."""
        self.should_fail = should_fail

    def reset(self):
        """Reset state."""
        self.response_index = 0
        self.call_log.clear()


# ============================================================================
# PYTEST FIXTURES
# ============================================================================


@pytest.fixture
def fake_llm_provider() -> FakeLLMProvider:
    """
    Provide FakeLLMProvider for testing.

    Usage:
        def test_llm(fake_llm_provider):
            fake_llm_provider.set_response("Hello", "Hi there!")
            response = await fake_llm_provider.generate("Hello")
            assert response.text == "Hi there!"
    """
    return FakeLLMProvider()


@pytest.fixture
def mock_gemini_client() -> MockGeminiClient:
    """
    Provide MockGeminiClient for testing.

    Usage:
        def test_gemini(mock_gemini_client):
            mock_gemini_client.set_responses(["Answer 1", "Answer 2"])
            result = await mock_gemini_client.generate_content("Question")
            assert result.text == "Answer 1"
    """
    return MockGeminiClient()


@pytest.fixture
def mock_ollama_client() -> MockOllamaClient:
    """
    Provide MockOllamaClient for testing.

    Usage:
        def test_ollama(mock_ollama_client):
            response = await mock_ollama_client.chat(
                model="llama2",
                messages=[{"role": "user", "content": "Hi"}]
            )
            assert response["message"]["content"]
    """
    return MockOllamaClient()


# ============================================================================
# FACTORY FUNCTION (for custom configurations)
# ============================================================================


def create_fake_llm(responses: Dict[str, str], **kwargs) -> FakeLLMProvider:
    """
    Factory function for creating FakeLLMProvider with custom config.

    Example:
        >>> llm = create_fake_llm(
        ...     responses={"prompt1": "response1"},
        ...     model_name="gpt-4",
        ...     should_fail=False
        ... )
    """
    return FakeLLMProvider(responses=responses, **kwargs)
