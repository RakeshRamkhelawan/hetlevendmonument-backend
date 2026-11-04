"""
ILLMSuggestionProvider -- LLM-agnostic interface voor twin suggesties.

Pattern: Dependency Injection + Protocol
Voordeel: Geen vendor lock-in, volledig testbaar via MockSuggestionProvider

Implementaties:
- GeminiSuggestionProvider (Google Gemini)
- ClaudeSuggestionProvider (Anthropic Claude)
- LocalSuggestionProvider (Ollama/lokale LLM)
- MockSuggestionProvider (tests)

Gebruik:
    provider: ILLMSuggestionProvider = GeminiSuggestionProvider(api_key="...")
    suggestion = await provider.suggest(context={...}, user_profile={...})
"""

import asyncio
import logging
import os
from typing import Protocol, TYPE_CHECKING, cast, Any
from src.core.shared.model_deur import bewaakt_model_aanroep

if TYPE_CHECKING:
    from google import genai
    from src.core.llm.llm_client import AnthropicClient
    from src.core.llm.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)


def _build_suggestion_prompt(
    context: dict[str, object],
    user_profile: dict[str, object],
) -> str:
    """Bouw een Nederlandse prompt voor struggle-analyse.

    Gedeeld door alle ILLMSuggestionProvider implementaties.
    """
    metrics = []
    if cast(int, context.get("recent_edits_same_line", 0)) > 0:
        metrics.append(f"- Herhaalde edits op dezelfde regel: {context['recent_edits_same_line']}")
    if cast(int, context.get("recent_file_switches", 0)) > 0:
        metrics.append(f"- Snelle bestandswissels: {context['recent_file_switches']}")
    if cast(int, context.get("lines_deleted_last_minute", 0)) > 0:
        metrics.append(f"- Verwijderde regels: {context['lines_deleted_last_minute']}")
    if cast(int, context.get("errors_last_minute", 0)) > 0:
        metrics.append(f"- Fouten laatste minuut: {context['errors_last_minute']}")

    profile_lines = []
    style = user_profile.get("coding_style", {})
    if style:
        profile_lines.append(f"- Programmeerstijl: {style}")
    patterns = user_profile.get("work_patterns", {})
    if patterns:
        profile_lines.append(f"- Werkpatronen: {patterns}")
    help_style = user_profile.get("optimal_help_style")
    if help_style:
        profile_lines.append(f"- Optimale hulpstijl: {help_style}")

    metrics_text = "\n".join(metrics) if metrics else "- Geen specifieke metrics gemeten."
    profile_text = (
        "\n".join(profile_lines) if profile_lines else "- Geen cognitief profiel beschikbaar."
    )

    return (
        "Je bent een empathische pair-programming partner. "
        "De gebruiker lijkt vast te zitten op basis van deze gedragsmetrics:\n\n"
        f"{metrics_text}\n\n"
        "Cognitief profiel van de gebruiker:\n"
        f"{profile_text}\n\n"
        "Geef EEN korte, concrete suggestie (max 2 zinnen) in het Nederlands "
        "om de gebruiker te helpen verder te komen. "
        "Geen uitleg over het model zelf, alleen de suggestie."
    )


class TokenUsage:
    """Token usage from a single LLM call."""

    def __init__(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class ILLMSuggestionProvider(Protocol):
    """
    Minimale interface voor LLM-suggesties in de digital twin.

    Elke implementatie moet suggest() asynchroon implementeren.
    Optioneel: get_last_token_usage() om token counts te rapporteren
                voor cost tracking.
    """

    async def suggest(
        self,
        context: dict[str, object],
        user_profile: dict[str, object],
    ) -> str:
        """
        Genereer een gepersonaliseerde suggestie op basis van context + profiel.

        Args:
            context: Geanonimiseerde gedragscontext (van PrivacyFilter)
            user_profile: Geleerd cognitief profiel van de user

        Returns:
            Suggestietekst in de taal van de user (NL of EN).
            Leeg string als geen suggestie mogelijk.
        """
        ...

    def get_last_token_usage(self) -> TokenUsage:
        """Return token usage from the last successful suggest() call."""
        return TokenUsage()


class MockSuggestionProvider:
    """
    Mock implementatie voor unit/integration tests.

    Geeft een vaste suggestietekst terug, zodat tests niet afhangen
    van echte LLM API calls.
    """

    def __init__(
        self,
        response: str = "Test suggestion",
        raise_error: bool = False,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ):
        self.response = response
        self.raise_error = raise_error
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self.call_count = 0
        self.last_context: dict[str, object] | None = None
        self.last_profile: dict[str, object] | None = None

    async def suggest(
        self,
        context: dict[str, object],
        user_profile: dict[str, object],
    ) -> str:
        self.call_count += 1
        self.last_context = context
        self.last_profile = user_profile

        if self.raise_error:
            raise RuntimeError("LLM provider unavailable")

        return self.response

    def get_last_token_usage(self) -> TokenUsage:
        return TokenUsage(input_tokens=self._input_tokens, output_tokens=self._output_tokens)


class TenantSuggestionProvider:
    """Suggesties van het taalmodel van de TENANT (brief 2026-10-20, ADR-041 B14).

    De keten van de twin koos haar model uit de omgevingssleutels (Anthropic, Google, Ollama) en eindigde in
    een vaste tekst; de keuze van de klant telde niet. Dit is de enige provider voor een tenantverzoek:
    `TenantTaalmodel` (de ene deur). Een storing geeft een LEGE suggestie (geen suggestie), nooit de tekst van
    een ander model.
    """

    def __init__(self, tenant_id: int) -> None:
        self._tenant_id = tenant_id
        # Noodstop (ronde 4): de provider kent zijn klant zelf, dus de controle hangt niet van de context af.
        self.noodstop_tenant_id = tenant_id
        self._usage = TokenUsage()

    @bewaakt_model_aanroep
    async def suggest(
        self,
        context: dict[str, object],
        user_profile: dict[str, object],
    ) -> str:
        from src.core.services.llm.tenant_deur import TenantTaalmodel

        prompt = _build_suggestion_prompt(context, user_profile)
        try:
            tekst, invoer, uitvoer = await TenantTaalmodel(self._tenant_id).tekst_met_gebruik(
                prompt, temperature=0.7, max_tokens=200
            )
        except Exception as exc:
            logger.error(
                "tenant_suggestion_failed tenant=%s: %s", self._tenant_id, type(exc).__name__, exc_info=True
            )
            self._usage = TokenUsage()
            return ""
        self._usage = TokenUsage(input_tokens=invoer, output_tokens=uitvoer)
        return tekst.strip()

    def get_last_token_usage(self) -> TokenUsage:
        return self._usage


class GeminiSuggestionProvider:
    """
    Google Gemini implementatie van ILLMSuggestionProvider.

    Gebruikt google.genai direct met asyncio.to_thread() om blocking calls
    async te maken. Retry met exponential backoff (3 pogingen).
    Fail-safe: bij elke fout wordt een lege string teruggegeven.
    """

    _MAX_RETRIES = 3
    _RETRY_DELAYS = [1.0, 2.0, 4.0]
    _DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self._model = model or self._DEFAULT_MODEL
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY", "")
        self._client: "genai.Client | None" = None
        self._initialized = False

    async def _ensure_initialized(self) -> bool:
        """Lazy initialize the Gemini client."""
        if self._initialized:
            return self._client is not None

        try:
            from google import genai

            if not self._api_key:
                return False

            self._client = genai.Client(api_key=self._api_key)
            self._initialized = True
            return True
        except Exception as exc:
            logger.warning("gemini_provider_init_failed: %s", str(exc))
            return False

    # _build_prompt is vervangen door de module-level _build_suggestion_prompt()
    _build_prompt = staticmethod(_build_suggestion_prompt)

    @bewaakt_model_aanroep
    async def suggest(
        self,
        context: dict[str, object],
        user_profile: dict[str, object],
    ) -> str:
        if not await self._ensure_initialized():
            return ""

        prompt = self._build_prompt(context, user_profile)
        last_error: Exception | None = None

        for attempt in range(self._MAX_RETRIES):
            try:
                from google.genai import types

                def _generate() -> Any:  # TODO(TYPE): replace Any with concrete type
                    if self._client is None:
                        raise RuntimeError("Gemini client not initialized")
                    return self._client.models.generate_content(
                        model=self._model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.7,
                            max_output_tokens=200,
                        ),
                    )

                response = await asyncio.to_thread(_generate)
                text = (
                    response.text
                    if response and hasattr(response, "text") and response.text
                    else ""
                )
                logger.debug(
                    "gemini_suggestion_generated model=%s attempt=%d len=%d",
                    self._model,
                    attempt + 1,
                    len(text),
                )
                return text.strip()
            except Exception as exc:
                last_error = exc
                if attempt < self._MAX_RETRIES - 1:
                    delay = self._RETRY_DELAYS[attempt]
                    logger.warning(
                        "gemini_suggestion_retry attempt=%d/%d delay=%.1fs error=%s",
                        attempt + 1,
                        self._MAX_RETRIES,
                        delay,
                        str(exc),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "gemini_suggestion_failed after %d retries: %s: %s",
                        self._MAX_RETRIES,
                        type(exc).__name__,
                        str(exc),
                    )

        return ""


class ClaudeSuggestionProvider:
    """
    Anthropic Claude implementatie van ILLMSuggestionProvider.

    Gebruikt de bestaande AnthropicClient uit src/core/llm.
    Retry met exponential backoff (3 pogingen).
    Fail-safe: bij elke fout wordt een lege string teruggegeven.
    """

    _MAX_RETRIES = 3
    _RETRY_DELAYS = [1.0, 2.0, 4.0]
    _DEFAULT_MODEL = "claude-3-5-sonnet"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self._model = model or self._DEFAULT_MODEL
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._client: "AnthropicClient | None" = None
        self._initialized = False

    async def _ensure_initialized(self) -> bool:
        """Lazy initialize the Anthropic client."""
        if self._initialized:
            return self._client is not None and getattr(self._client, "_available", False)

        try:
            from src.core.llm.llm_client import (
                AnthropicClient,
                LLMConfig,
                LLMModel,
                LLMProvider,
            )

            if not self._api_key:
                return False

            config = LLMConfig(
                provider=LLMProvider.ANTHROPIC,
                model=LLMModel.CLAUDE_3_5_SONNET,
                api_key=self._api_key,
                max_tokens=200,
                temperature=0.7,
            )
            self._client = AnthropicClient(config)
            self._initialized = True
            return self._client._available
        except Exception as exc:
            logger.warning("claude_provider_init_failed: %s", str(exc))
            return False

    @bewaakt_model_aanroep
    async def suggest(
        self,
        context: dict[str, object],
        user_profile: dict[str, object],
    ) -> str:
        if not await self._ensure_initialized():
            return ""

        prompt = _build_suggestion_prompt(context, user_profile)
        last_error: Exception | None = None

        for attempt in range(self._MAX_RETRIES):
            try:
                if self._client is None:
                    raise RuntimeError("Claude client not initialized")
                response = await self._client.text_completion(
                    prompt,
                    max_tokens=200,
                    temperature=0.7,
                )
                text = response.content if response and response.success else ""
                logger.debug(
                    "claude_suggestion_generated model=%s attempt=%d len=%d",
                    self._model,
                    attempt + 1,
                    len(text),
                )
                return text.strip()
            except Exception as exc:
                last_error = exc
                if attempt < self._MAX_RETRIES - 1:
                    delay = self._RETRY_DELAYS[attempt]
                    logger.warning(
                        "claude_suggestion_retry attempt=%d/%d delay=%.1fs error=%s",
                        attempt + 1,
                        self._MAX_RETRIES,
                        delay,
                        str(exc),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "claude_suggestion_failed after %d retries: %s: %s",
                        self._MAX_RETRIES,
                        type(exc).__name__,
                        str(exc),
                    )

        return ""


class LocalSuggestionProvider:
    """
    Ollama/lokale LLM implementatie van ILLMSuggestionProvider.

    Gebruikt de bestaande OllamaProvider uit src/core/llm.
    Voordeel: Geen API kosten, werkt offline.
    Retry met exponential backoff (3 pogingen).
    Fail-safe: bij elke fout wordt een lege string teruggegeven.
    """

    _MAX_RETRIES = 3
    _RETRY_DELAYS = [1.0, 2.0, 4.0]

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self._base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._model = model or os.getenv("OLLAMA_MODEL", "llama3.1:latest")
        self._provider: "OllamaProvider | None" = None
        self._initialized = False

    async def _ensure_initialized(self) -> bool:
        """Lazy initialize the Ollama client."""
        if self._initialized:
            return self._provider is not None

        try:
            from src.core.llm.ollama_provider import OllamaProvider

            self._provider = OllamaProvider(base_url=self._base_url)
            self._initialized = await self._provider.initialize()
            return self._initialized
        except Exception as exc:
            logger.warning("local_provider_init_failed: %s", str(exc))
            return False

    @bewaakt_model_aanroep
    async def suggest(
        self,
        context: dict[str, object],
        user_profile: dict[str, object],
    ) -> str:
        if not await self._ensure_initialized():
            return ""

        prompt = _build_suggestion_prompt(context, user_profile)
        last_error: Exception | None = None

        for attempt in range(self._MAX_RETRIES):
            try:
                if self._provider is None:
                    raise RuntimeError("Local provider not initialized")
                response = await self._provider.generate_response(
                    prompt,
                    model=self._model,
                    max_tokens=200,
                    temperature=0.7,
                )
                text = cast(str, response.get("content", "")) if response.get("success") else ""
                logger.debug(
                    "local_suggestion_generated model=%s attempt=%d len=%d",
                    self._model,
                    attempt + 1,
                    len(text),
                )
                return text.strip()
            except Exception as exc:
                last_error = exc
                if attempt < self._MAX_RETRIES - 1:
                    delay = self._RETRY_DELAYS[attempt]
                    logger.warning(
                        "local_suggestion_retry attempt=%d/%d delay=%.1fs error=%s",
                        attempt + 1,
                        self._MAX_RETRIES,
                        delay,
                        str(exc),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "local_suggestion_failed after %d retries: %s: %s",
                        self._MAX_RETRIES,
                        type(exc).__name__,
                        str(exc),
                    )

        return ""
