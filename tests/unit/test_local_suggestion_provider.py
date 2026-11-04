"""Unit tests for LocalSuggestionProvider (Digital Twin Phase 3.4).

Covers:
- Happy path: successful suggestion via OllamaProvider
- Retry logic: transient failures are retried
- Fallback: returns empty string after exhausting retries
- Initialization failure: returns empty string when Ollama is unavailable
- Prompt building: includes metrics and profile
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.learning.interfaces.llm_provider import (
    LocalSuggestionProvider,
    _build_suggestion_prompt,
)


@pytest.mark.asyncio
async def test_suggest_happy_path() -> None:
    """Successful suggestion returns stripped text."""
    provider = LocalSuggestionProvider(base_url="http://localhost:11434")

    with patch("src.core.llm.ollama_provider.OllamaProvider") as mock_provider_class:
        mock_ollama = MagicMock()
        mock_ollama.initialize = AsyncMock(return_value=True)
        mock_ollama.generate_response = AsyncMock(
            return_value={
                "success": True,
                "content": "  Neem een korte pauze!  ",
            }
        )
        mock_provider_class.return_value = mock_ollama

        result = await provider.suggest(
            context={"recent_edits_same_line": 5},
            user_profile={"optimal_help_style": "direct"},
        )

    assert result == "Neem een korte pauze!"
    assert mock_ollama.generate_response.call_count == 1


@pytest.mark.asyncio
async def test_suggest_retries_on_failure() -> None:
    """Transient failures trigger retries; success on 2nd attempt."""
    provider = LocalSuggestionProvider(base_url="http://localhost:11434")

    with patch("src.core.llm.ollama_provider.OllamaProvider") as mock_provider_class:
        mock_ollama = MagicMock()
        mock_ollama.initialize = AsyncMock(return_value=True)
        mock_ollama.generate_response = AsyncMock(
            side_effect=[
                ConnectionError("network error"),
                {"success": True, "content": "Werkt na retry"},
            ]
        )
        mock_provider_class.return_value = mock_ollama

        with patch("asyncio.sleep") as mock_sleep:
            result = await provider.suggest(
                context={"recent_file_switches": 3},
                user_profile={},
            )

    assert result == "Werkt na retry"
    assert mock_ollama.generate_response.call_count == 2
    mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_suggest_returns_empty_after_exhausted_retries() -> None:
    """All retries exhausted -> returns empty string, no crash."""
    provider = LocalSuggestionProvider(base_url="http://localhost:11434")

    with patch("src.core.llm.ollama_provider.OllamaProvider") as mock_provider_class:
        mock_ollama = MagicMock()
        mock_ollama.initialize = AsyncMock(return_value=True)
        mock_ollama.generate_response = AsyncMock(side_effect=ConnectionError("always fails"))
        mock_provider_class.return_value = mock_ollama

        with patch("asyncio.sleep") as mock_sleep:
            result = await provider.suggest(
                context={"errors_last_minute": 10},
                user_profile={},
            )

    assert result == ""
    assert mock_ollama.generate_response.call_count == 3
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_suggest_returns_empty_when_ollama_unavailable() -> None:
    """Ollama init fails -> returns empty string immediately."""
    provider = LocalSuggestionProvider(base_url="http://localhost:11434")

    with patch("src.core.llm.ollama_provider.OllamaProvider") as mock_provider_class:
        mock_ollama = MagicMock()
        mock_ollama.initialize = AsyncMock(return_value=False)
        mock_provider_class.return_value = mock_ollama

        result = await provider.suggest(context={}, user_profile={})

    assert result == ""
    mock_ollama.generate_response.assert_not_called()


@pytest.mark.asyncio
async def test_suggest_empty_response_content() -> None:
    """Ollama returns empty content -> returns empty string."""
    provider = LocalSuggestionProvider(base_url="http://localhost:11434")

    with patch("src.core.llm.ollama_provider.OllamaProvider") as mock_provider_class:
        mock_ollama = MagicMock()
        mock_ollama.initialize = AsyncMock(return_value=True)
        mock_ollama.generate_response = AsyncMock(return_value={"success": True, "content": ""})
        mock_provider_class.return_value = mock_ollama

        result = await provider.suggest(context={}, user_profile={})

    assert result == ""


@pytest.mark.asyncio
async def test_suggest_uses_custom_model_from_env() -> None:
    """Provider respects OLLAMA_MODEL env var."""
    with patch.dict(os.environ, {"OLLAMA_MODEL": "mistral-nemo:latest"}):
        provider = LocalSuggestionProvider()
        assert provider._model == "mistral-nemo:latest"


def test_build_prompt_includes_metrics_and_profile() -> None:
    """Prompt builder includes behavior metrics and user profile."""
    context = {
        "recent_edits_same_line": 8,
        "recent_file_switches": 5,
        "lines_deleted_last_minute": 60,
        "errors_last_minute": 6,
    }
    user_profile = {
        "coding_style": {"prefers_tdd": True},
        "optimal_help_style": "direct",
    }

    prompt = _build_suggestion_prompt(context, user_profile)

    assert "Herhaalde edits" in prompt
    assert "bestandswissels" in prompt
    assert "Verwijderde regels" in prompt
    assert "Fouten" in prompt
    assert "direct" in prompt
    assert "Nederlands" in prompt
