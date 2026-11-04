"""Tests for ILLMSuggestionProvider implementations.

Covers:
- GeminiSuggestionProvider (Google Gemini adapter)
- ClaudeSuggestionProvider (Anthropic Claude adapter)
- LocalSuggestionProvider (Ollama/local adapter)
- MockSuggestionProvider (test stub)

Happy path: suggest() returns non-empty text.
Unhappy paths:
- No API key / unavailable → returns empty string, no exception.
- API error (timeout, 429, 500) → retries 3x, then returns empty string.
- Empty response → returns empty string.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.learning.interfaces.llm_provider import (
    ClaudeSuggestionProvider,
    GeminiSuggestionProvider,
    LocalSuggestionProvider,
    MockSuggestionProvider,
    _build_suggestion_prompt,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_CONTEXT = {"recent_edits_same_line": 3, "errors_last_minute": 2}
_SAMPLE_PROFILE = {"coding_style": {"language": "python"}, "optimal_help_style": "step_by_step"}


# ---------------------------------------------------------------------------
# _build_suggestion_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_includes_metrics_and_profile() -> None:
    prompt = _build_suggestion_prompt(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)
    assert "Herhaalde edits" in prompt
    assert "Fouten laatste minuut" in prompt
    assert "step_by_step" in prompt
    assert "Nederlands" in prompt


def test_build_prompt_with_empty_inputs() -> None:
    prompt = _build_suggestion_prompt({}, {})
    assert "Geen specifieke metrics" in prompt
    assert "Geen cognitief profiel" in prompt


# ---------------------------------------------------------------------------
# MockSuggestionProvider
# ---------------------------------------------------------------------------


class TestMockSuggestionProvider:
    @pytest.mark.asyncio
    async def test_returns_configured_response(self) -> None:
        provider = MockSuggestionProvider(response="Test antwoord")
        result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)
        assert result == "Test antwoord"
        assert provider.call_count == 1

    @pytest.mark.asyncio
    async def test_raises_when_configured(self) -> None:
        provider = MockSuggestionProvider(raise_error=True)
        with pytest.raises(RuntimeError, match="LLM provider unavailable"):
            await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)

    @pytest.mark.asyncio
    async def test_stores_last_context_and_profile(self) -> None:
        provider = MockSuggestionProvider()
        await provider.suggest({"a": 1}, {"b": 2})
        assert provider.last_context == {"a": 1}
        assert provider.last_profile == {"b": 2}


# ---------------------------------------------------------------------------
# GeminiSuggestionProvider
# ---------------------------------------------------------------------------


class TestGeminiSuggestionProvider:
    @pytest.mark.asyncio
    async def test_suggest_happy_path(self) -> None:
        provider = GeminiSuggestionProvider(api_key="fake-key")

        mock_response = MagicMock()
        mock_response.text = "  Neem een korte pauze.  "

        with patch.object(provider, "_ensure_initialized", return_value=True):
            provider._client = MagicMock()
            provider._client.models.generate_content.return_value = mock_response

            result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)

        assert result == "Neem een korte pauze."

    @pytest.mark.asyncio
    async def test_returns_empty_when_not_initialized(self) -> None:
        provider = GeminiSuggestionProvider(api_key="")
        result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)
        assert result == ""

    @pytest.mark.asyncio
    async def test_retries_on_error_and_returns_empty(self) -> None:
        provider = GeminiSuggestionProvider(api_key="fake-key")

        with patch.object(provider, "_ensure_initialized", return_value=True):
            provider._client = MagicMock()
            provider._client.models.generate_content.side_effect = RuntimeError("timeout")

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)

        assert result == ""
        assert provider._client.models.generate_content.call_count == 3

    @pytest.mark.asyncio
    async def test_returns_empty_on_empty_response(self) -> None:
        provider = GeminiSuggestionProvider(api_key="fake-key")

        mock_response = MagicMock()
        mock_response.text = None

        with patch.object(provider, "_ensure_initialized", return_value=True):
            provider._client = MagicMock()
            provider._client.models.generate_content.return_value = mock_response

            result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)

        assert result == ""


# ---------------------------------------------------------------------------
# ClaudeSuggestionProvider
# ---------------------------------------------------------------------------


class TestClaudeSuggestionProvider:
    @pytest.mark.asyncio
    async def test_suggest_happy_path(self) -> None:
        provider = ClaudeSuggestionProvider(api_key="fake-key")

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.content = "  Vraag hulp aan een collega.  "

        with patch.object(provider, "_ensure_initialized", return_value=True):
            provider._client = MagicMock()
            provider._client.text_completion = AsyncMock(return_value=mock_response)

            result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)

        assert result == "Vraag hulp aan een collega."

    @pytest.mark.asyncio
    async def test_returns_empty_when_not_initialized(self) -> None:
        provider = ClaudeSuggestionProvider(api_key="")
        result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)
        assert result == ""

    @pytest.mark.asyncio
    async def test_retries_on_error_and_returns_empty(self) -> None:
        provider = ClaudeSuggestionProvider(api_key="fake-key")

        with patch.object(provider, "_ensure_initialized", return_value=True):
            provider._client = MagicMock()
            provider._client.text_completion = AsyncMock(side_effect=RuntimeError("429"))

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)

        assert result == ""
        assert provider._client.text_completion.call_count == 3

    @pytest.mark.asyncio
    async def test_returns_empty_on_failed_response(self) -> None:
        provider = ClaudeSuggestionProvider(api_key="fake-key")

        mock_response = MagicMock()
        mock_response.success = False
        mock_response.content = ""

        with patch.object(provider, "_ensure_initialized", return_value=True):
            provider._client = MagicMock()
            provider._client.text_completion = AsyncMock(return_value=mock_response)

            result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)

        assert result == ""


# ---------------------------------------------------------------------------
# LocalSuggestionProvider
# ---------------------------------------------------------------------------


class TestLocalSuggestionProvider:
    @pytest.mark.asyncio
    async def test_suggest_happy_path(self) -> None:
        provider = LocalSuggestionProvider(base_url="http://localhost:11434")

        with patch.object(provider, "_ensure_initialized", return_value=True):
            provider._provider = MagicMock()
            provider._provider.generate_response = AsyncMock(
                return_value={"success": True, "content": "  Denk na over je aanpak.  "}
            )

            result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)

        assert result == "Denk na over je aanpak."

    @pytest.mark.asyncio
    async def test_returns_empty_when_not_initialized(self) -> None:
        provider = LocalSuggestionProvider(base_url="")
        result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)
        assert result == ""

    @pytest.mark.asyncio
    async def test_retries_on_error_and_returns_empty(self) -> None:
        provider = LocalSuggestionProvider(base_url="http://localhost:11434")

        with patch.object(provider, "_ensure_initialized", return_value=True):
            provider._provider = MagicMock()
            provider._provider.generate_response = AsyncMock(side_effect=RuntimeError("timeout"))

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)

        assert result == ""
        assert provider._provider.generate_response.call_count == 3

    @pytest.mark.asyncio
    async def test_returns_empty_on_failed_response(self) -> None:
        provider = LocalSuggestionProvider(base_url="http://localhost:11434")

        with patch.object(provider, "_ensure_initialized", return_value=True):
            provider._provider = MagicMock()
            provider._provider.generate_response = AsyncMock(return_value={"success": False})

            result = await provider.suggest(_SAMPLE_CONTEXT, _SAMPLE_PROFILE)

        assert result == ""


# ---------------------------------------------------------------------------
# Provider selection matrix (_select_llm_provider)
# ---------------------------------------------------------------------------


class TestSelectLLMProvider:
    """De keten van de twin is het model van de TENANT; omgevingssleutels kiezen niets meer (brief 2026-10-20)."""

    def test_selects_mock_when_explicitly_configured(self) -> None:
        env = {"LLM_PROVIDER": "mock"}
        with patch.dict("os.environ", env, clear=False):
            from src.core.learning.services.twin_service_factory import _build_provider_chain

            chain = _build_provider_chain(7, eu_only=False)
            assert len(chain) == 1
            assert isinstance(chain[0], MockSuggestionProvider)

    @pytest.mark.parametrize(
        "sleutel,waarde",
        [
            ("ANTHROPIC_API_KEY", "sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxx"),
            ("GOOGLE_API_KEY", "AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"),
            ("OLLAMA_BASE_URL", "http://localhost:11434"),
        ],
    )
    def test_een_omgevingssleutel_kiest_geen_andere_leverancier(self, sleutel: str, waarde: str) -> None:
        env = {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "OLLAMA_BASE_URL": "", "LLM_PROVIDER": ""}
        env[sleutel] = waarde
        with patch.dict("os.environ", env, clear=False):
            from src.core.learning.services.twin_service_factory import _build_provider_chain

            chain = _build_provider_chain(7, eu_only=False)
            assert [type(p).__name__ for p in chain] == ["TenantSuggestionProvider"]

    def test_zonder_sleutels_is_het_nog_steeds_het_model_van_de_tenant(self) -> None:
        env = {"ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "OLLAMA_BASE_URL": "", "LLM_PROVIDER": ""}
        with patch.dict("os.environ", env, clear=False):
            from src.core.learning.services.twin_service_factory import _build_provider_chain

            chain = _build_provider_chain(7, eu_only=False)
            assert [type(p).__name__ for p in chain] == ["TenantSuggestionProvider"]
