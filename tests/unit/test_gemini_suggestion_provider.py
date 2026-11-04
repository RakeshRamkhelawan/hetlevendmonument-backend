"""Unit tests for GeminiSuggestionProvider (Phase 5).

Covers:
- Happy path: successful suggestion generation
- Retry logic: transient failures are retried
- Fallback: returns empty string after exhausting retries
- Initialization failure: returns empty string when API key is missing
- Prompt building: includes metrics and profile
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.learning.interfaces.llm_provider import GeminiSuggestionProvider


class FakeResponse:
    """Fake Gemini response for testing."""

    def __init__(self, text: str):
        self.text = text


@pytest.mark.asyncio
async def test_suggest_happy_path() -> None:
    """Successful suggestion returns stripped text."""
    provider = GeminiSuggestionProvider(api_key="test-key-12345678901234567890")

    fake_response = FakeResponse("  Neem een korte pauze!  ")

    with patch("google.genai.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response
        mock_client_class.return_value = mock_client

        result = await provider.suggest(
            context={"recent_edits_same_line": 5},
            user_profile={"optimal_help_style": "direct"},
        )

    assert result == "Neem een korte pauze!"
    assert mock_client.models.generate_content.call_count == 1


@pytest.mark.asyncio
async def test_suggest_retries_on_failure() -> None:
    """Transient failures trigger retries; success on 2nd attempt."""
    provider = GeminiSuggestionProvider(api_key="test-key-12345678901234567890")

    fake_response = FakeResponse("Werkt na retry")

    with patch("google.genai.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [
            ConnectionError("network error"),
            fake_response,
        ]
        mock_client_class.return_value = mock_client

        with patch("asyncio.sleep") as mock_sleep:
            result = await provider.suggest(
                context={"recent_file_switches": 3},
                user_profile={},
            )

    assert result == "Werkt na retry"
    assert mock_client.models.generate_content.call_count == 2
    mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_suggest_returns_empty_after_exhausted_retries() -> None:
    """All retries exhausted -> returns empty string, no crash."""
    provider = GeminiSuggestionProvider(api_key="test-key-12345678901234567890")

    with patch("google.genai.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = ConnectionError("always fails")
        mock_client_class.return_value = mock_client

        with patch("asyncio.sleep") as mock_sleep:
            result = await provider.suggest(
                context={"errors_last_minute": 10},
                user_profile={},
            )

    assert result == ""
    assert mock_client.models.generate_content.call_count == 3
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_suggest_returns_empty_without_api_key() -> None:
    """No API key -> returns empty string immediately."""
    provider = GeminiSuggestionProvider(api_key="")

    result = await provider.suggest(context={}, user_profile={})
    assert result == ""


@pytest.mark.asyncio
async def test_suggest_empty_response_text() -> None:
    """Gemini returns None text -> returns empty string."""
    provider = GeminiSuggestionProvider(api_key="test-key-12345678901234567890")

    fake_response = FakeResponse("")

    with patch("google.genai.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response
        mock_client_class.return_value = mock_client

        result = await provider.suggest(context={}, user_profile={})

    assert result == ""


def test_build_prompt_includes_metrics_and_profile() -> None:
    """Prompt builder includes behavior metrics and user profile."""
    provider = GeminiSuggestionProvider(api_key="test-key")

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

    prompt = provider._build_prompt(context, user_profile)

    assert "Herhaalde edits" in prompt
    assert "bestandswissels" in prompt
    assert "Verwijderde regels" in prompt
    assert "Fouten" in prompt
    assert "direct" in prompt
    assert "Nederlands" in prompt
