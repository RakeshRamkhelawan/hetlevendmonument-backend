"""Unit tests for ClaudeSuggestionProvider (Digital Twin Phase 3.4).

Covers:
- Happy path: successful suggestion via AnthropicClient
- Retry logic: transient failures are retried
- Fallback: returns empty string after exhausting retries
- Initialization failure: returns empty string when API key is missing
- Prompt building: includes metrics and profile
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.learning.interfaces.llm_provider import (
    ClaudeSuggestionProvider,
    _build_suggestion_prompt,
)


@pytest.mark.asyncio
async def test_suggest_happy_path() -> None:
    """Successful suggestion returns stripped text."""
    provider = ClaudeSuggestionProvider(api_key="sk-ant-api03-test-key-1234567890")

    fake_response = MagicMock()
    fake_response.content = "  Neem een korte pauze!  "
    fake_response.success = True

    with patch("src.core.llm.llm_client.AnthropicClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client._available = True
        mock_client.text_completion = AsyncMock(return_value=fake_response)
        mock_client_class.return_value = mock_client

        result = await provider.suggest(
            context={"recent_edits_same_line": 5},
            user_profile={"optimal_help_style": "direct"},
        )

    assert result == "Neem een korte pauze!"
    assert mock_client.text_completion.call_count == 1


@pytest.mark.asyncio
async def test_suggest_retries_on_failure() -> None:
    """Transient failures trigger retries; success on 2nd attempt."""
    provider = ClaudeSuggestionProvider(api_key="sk-ant-api03-test-key-1234567890")

    fake_response = MagicMock()
    fake_response.content = "Werkt na retry"
    fake_response.success = True

    with patch("src.core.llm.llm_client.AnthropicClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client._available = True
        mock_client.text_completion = AsyncMock(
            side_effect=[ConnectionError("network error"), fake_response]
        )
        mock_client_class.return_value = mock_client

        with patch("asyncio.sleep") as mock_sleep:
            result = await provider.suggest(
                context={"recent_file_switches": 3},
                user_profile={},
            )

    assert result == "Werkt na retry"
    assert mock_client.text_completion.call_count == 2
    mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_suggest_returns_empty_after_exhausted_retries() -> None:
    """All retries exhausted -> returns empty string, no crash."""
    provider = ClaudeSuggestionProvider(api_key="sk-ant-api03-test-key-1234567890")

    with patch("src.core.llm.llm_client.AnthropicClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client._available = True
        mock_client.text_completion = AsyncMock(side_effect=ConnectionError("always fails"))
        mock_client_class.return_value = mock_client

        with patch("asyncio.sleep") as mock_sleep:
            result = await provider.suggest(
                context={"errors_last_minute": 10},
                user_profile={},
            )

    assert result == ""
    assert mock_client.text_completion.call_count == 3
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_suggest_returns_empty_without_api_key() -> None:
    """No API key -> returns empty string immediately."""
    provider = ClaudeSuggestionProvider(api_key="")

    result = await provider.suggest(context={}, user_profile={})
    assert result == ""


@pytest.mark.asyncio
async def test_suggest_empty_response_content() -> None:
    """Anthropic returns empty content -> returns empty string."""
    provider = ClaudeSuggestionProvider(api_key="sk-ant-api03-test-key-1234567890")

    fake_response = MagicMock()
    fake_response.content = ""
    fake_response.success = True

    with patch("src.core.llm.llm_client.AnthropicClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client._available = True
        mock_client.text_completion = AsyncMock(return_value=fake_response)
        mock_client_class.return_value = mock_client

        result = await provider.suggest(context={}, user_profile={})

    assert result == ""


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
