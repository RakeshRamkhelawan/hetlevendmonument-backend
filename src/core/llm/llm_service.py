"""
LLM Service Manager
Manages LLM provider initialization and request routing
"""

import logging
import os
from collections.abc import Callable
from typing import Any, cast

from src.core.shared.model_deur import bewaakt_model_aanroep
from src.core.governance.gdpr_enforcer import GDPREnforcer

from .gemini_provider import GeminiProvider
from .llm_client import LLMMessage, LLMProvider, LLMResponse, ModelInfo
from .mistral_provider import MistralProvider
from .mock_provider import MockProvider
from .ollama_provider import OllamaProvider

__all__ = ["LLMService", "LLMProvider", "ModelInfo"]

logger = logging.getLogger(__name__)


class LLMService:
    """Central LLM service with provider management"""

    _instance: "LLMService | None" = None

    def __new__(cls) -> "LLMService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized_service = False
        return cls._instance

    initialized_service: bool

    def __init__(self) -> None:
        # Initialize only once
        if hasattr(self, "providers"):
            return
        self.providers: dict[LLMProvider, Any] = {}  # TODO(TYPE): replace Any with concrete type
        # Mistral (EU) is de standaard voor klantgegevens (ADR-041 B14, besluit Rakesh 2026-10-15).
        self.default_provider = LLMProvider.MISTRAL
        self.default_model = "mistral-small-latest"
        self.initialized = False

        # Phase 1 Enhancement: Token budget tracking
        self._tokens_used = 0
        self.token_budget: int | None = None
        self._gdpr_enforcer = GDPREnforcer()

    # Phase 1 Enhancement: Token budget management
    def set_token_budget(self, budget: int) -> None:
        """Set a token budget for the service"""
        self.token_budget = budget

    def reset_token_counter(self) -> None:
        """Reset the used tokens counter to 0"""
        self._tokens_used = 0

    @property
    def tokens_remaining(self) -> int | None:
        """Return remaining tokens in budget, or None if unlimited"""
        if self.token_budget is None:
            return None
        return max(0, self.token_budget - self._tokens_used)

    async def initialize(self) -> None:
        """Initialize available LLM providers asynchronously"""
        if self.initialized:
            return

        # 0. Check for explicit Mock Mode (Dev/Test)
        if os.getenv("LLM_PROVIDER") == "mock":
            mock_provider = MockProvider()
            if await mock_provider.initialize():
                self.providers[LLMProvider.MOCK] = mock_provider
                self.default_provider = LLMProvider.MOCK
                self.default_model = "mock-model"
                # Een UITDRUKKELIJKE keuze, dus toegestaan, maar nooit onopgemerkt: elk antwoord
                # is nep (ADR-041 B14: geen stille namaak).
                logger.warning(
                    "[MOCK] LLM_PROVIDER=mock: NAMAAK-TAALMODEL ACTIEF, antwoorden zijn niet echt"
                )
                self.initialized = True
                return

        configured_provider = os.getenv("LLM_PROVIDER", "").lower()
        if configured_provider == "deepseek" and os.getenv("MISTRAL_API_KEY"):
            # De uitrol (CD) zet nog `LLM_PROVIDER=deepseek`; DeepSeek mag niet met klantgegevens
            # (ADR-041 B14). Met een Mistralsleutel wordt het Mistral en blijft DeepSeek uit.
            logger.warning(
                "LLM_PROVIDER=deepseek wordt genegeerd omdat MISTRAL_API_KEY gezet is: Mistral (EU) "
                "wordt gebruikt (ADR-041 B14)"
            )
            configured_provider = "mistral"

        # 0b. Mistral (EU): het standaardmodel voor klantgegevens (ADR-041 B14).
        try:
            mistral_api_key = os.getenv("MISTRAL_API_KEY")
            if mistral_api_key:
                mistral_provider = MistralProvider(api_key=mistral_api_key)
                if await mistral_provider.initialize():
                    self.providers[LLMProvider.MISTRAL] = mistral_provider
                    logger.info("Mistral provider initialized (EU)")
                else:
                    logger.warning("Mistral provider failed to initialize")
            else:
                logger.info("MISTRAL_API_KEY not found - trying next provider")
        except Exception as e:
            logger.error("Failed to initialize Mistral provider: %s", type(e).__name__)

        # 1. DeepSeek is er NIET meer, ook niet bij `LLM_PROVIDER=deepseek` met een gezette
        # `DEEPSEEK_API_KEY`: deze service draait over klantgegevens en DeepSeek (China, geen
        # verwerkersovereenkomst) mag daar niet mee (ADR-041 B14, brief 2026-10-19).
        if configured_provider == "deepseek":
            logger.error(
                "LLM_PROVIDER=deepseek wordt NIET uitgevoerd: DeepSeek mag niet met klantgegevens "
                "(ADR-041 B14). Zet MISTRAL_API_KEY en LLM_PROVIDER=mistral."
            )

        # 2. Initialize Google Gemini (Secondary Priority)
        try:
            google_api_key = os.getenv("GOOGLE_API_KEY")
            if google_api_key:
                gemini_provider = GeminiProvider(google_api_key)
                success = await gemini_provider.initialize()

                if success:
                    self.providers[LLMProvider.GOOGLE] = gemini_provider
                    logger.info("Google Gemini provider initialized")
                else:
                    logger.warning("Google Gemini provider failed to initialize")
            else:
                logger.info("GOOGLE_API_KEY not found - trying next provider")
        except Exception as e:
            logger.error("Failed to initialize Google provider: %s", e)

        # 3. Initialize Anthropic Claude
        try:
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
            if anthropic_api_key:
                from src.core.llm.llm_client import (
                    AnthropicClient,
                    LLMConfig,
                    LLMModel,
                )
                from src.core.llm.llm_client import LLMProvider as LLMProviderEnum

                config = LLMConfig(
                    provider=LLMProviderEnum.ANTHROPIC,
                    model=LLMModel.CLAUDE_3_5_SONNET,
                    api_key=anthropic_api_key,
                    max_tokens=2000,
                    temperature=0.7,
                )
                anthropic_client = AnthropicClient(config)
                if anthropic_client._available:
                    self.providers[LLMProvider.ANTHROPIC] = anthropic_client
                    logger.info("Anthropic provider initialized")
                else:
                    logger.warning("Anthropic provider not available (check API key)")
            else:
                logger.info("ANTHROPIC_API_KEY not found - trying next provider")
        except Exception as e:
            logger.error("Failed to initialize Anthropic provider: %s", e)

        # 4. Initialize Ollama (LAST Priority - Local Fallback)
        try:
            ollama_provider = OllamaProvider()
            if await ollama_provider.initialize():
                self.providers[LLMProvider.OLLAMA] = ollama_provider
                logger.info("Ollama provider initialized (Local)")
            else:
                logger.info("Ollama not running - local models unavailable")
        except Exception as e:
            logger.warning("Ollama provider not available: %s", e)

        # 5. Determine Default Provider based on Preference & Availability
        if configured_provider == "mistral" and LLMProvider.MISTRAL in self.providers:
            self.default_provider = LLMProvider.MISTRAL
            self.default_model = "mistral-small-latest"
            logger.info("Selected Mistral as DEFAULT provider (User Preference)")

        elif configured_provider == "google" and LLMProvider.GOOGLE in self.providers:
            self.default_provider = LLMProvider.GOOGLE
            self.default_model = "gemini-2.5-flash"
            logger.info("Selected Google Gemini as DEFAULT provider (User Preference)")

        elif configured_provider == "anthropic" and LLMProvider.ANTHROPIC in self.providers:
            self.default_provider = LLMProvider.ANTHROPIC
            self.default_model = "claude-3-5-sonnet"
            logger.info("Selected Anthropic as DEFAULT provider (User Preference)")

        elif configured_provider == "ollama" and LLMProvider.OLLAMA in self.providers:
            self.default_provider = LLMProvider.OLLAMA
            self.default_model = "llama3.2:3b"
            logger.info("Selected Ollama as DEFAULT provider (User Preference)")

        else:
            # Fallback logic: Mistral (EU) > Gemini > Anthropic > Ollama (DeepSeek alleen uitdrukkelijk).
            # Dit is een keuze bij het OPSTARTEN op grond van de gezette sleutels, geen failover tijdens
            # het draaien: een omgeving zonder Mistralsleutel is bewust anders ingericht. Er is geen
            # code die bij een storing van Mistral naar Google of Anthropic overschakelt.
            if LLMProvider.MISTRAL in self.providers:
                self.default_provider = LLMProvider.MISTRAL
                self.default_model = "mistral-small-latest"
                logger.info("Fallback Default: Mistral")
            elif LLMProvider.GOOGLE in self.providers:
                self.default_provider = LLMProvider.GOOGLE
                self.default_model = "gemini-2.5-flash"
                logger.info("Fallback Default: Google Gemini")
            elif LLMProvider.ANTHROPIC in self.providers:
                self.default_provider = LLMProvider.ANTHROPIC
                self.default_model = "claude-3-5-sonnet"
                logger.info("Fallback Default: Anthropic")
            elif LLMProvider.OLLAMA in self.providers:
                self.default_provider = LLMProvider.OLLAMA
                self.default_model = "llama3:latest"
                logger.info("Fallback Default: Ollama")
            # If no providers, mock logic below handles it

        if not self.providers:
            if os.environ.get("TESTING", "").strip().lower() in {"1", "true", "yes"}:
                logger.warning(
                    "[MOCK] geen echte LLM-provider: namaakmodel actief (alleen tests)"
                )
                mock_provider = MockProvider()
                if await mock_provider.initialize():
                    self.providers[LLMProvider.MOCK] = mock_provider
                    self.default_provider = LLMProvider.MOCK
                    self.default_model = "mock-model"
            else:
                # Geen stille namaak: een aanroep geeft nu een duidelijke fout
                # ("Provider ... not initialized") in plaats van een verzonnen antwoord.
                logger.error(
                    "Geen enkele LLM-provider beschikbaar: zet MISTRAL_API_KEY of start Ollama. "
                    "Er is bewust GEEN namaakmodel als terugval."
                )
        else:
            logger.info(
                f"Initialized providers: {[p.value for p in self.providers.keys()]}, Default: {self.default_provider.value}"
            )

        self.initialized = True

    @bewaakt_model_aanroep
    async def generate_response(
        self,
        prompt: str,
        provider: LLMProvider | None = None,
        model: str | None = None,
        tools: list[
            Any  # TODO(TYPE): replace Any with concrete type
        ]  # NOTE: Gemini passes list[Callable], Ollama/OpenAI passes list[dict[str,object]] -- cannot narrow
        | None = None,  # ENHANCEMENT 1: Add tools parameter
        automatic_function_calling: bool = False,  # ENHANCEMENT 1: Add automatic calling flag
        max_retries: int = 3,  # Phase 1: Retry logic
        **kwargs: Any,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate response using specified or default provider.

        ENHANCEMENT 1: Now supports function calling via tools parameter.
        Phase 1 Enhancement: Exception hierarchy, retry logic with exponential backoff.

        Args:
            prompt: The text prompt for generation
            provider: LLM provider to use (defaults to self.default_provider)
            model: Model name to use (defaults to self.default_model)
            tools: Optional list of callable functions for function calling
            automatic_function_calling: If True, SDK handles execution; if False, returns function call parts
            max_retries: Maximum retry attempts on transient errors (default 3)
            **kwargs: Additional provider-specific parameters

        Returns: Dict[str, Any] with response data, may include 'function_calls' if tools were provided  # TODO(TYPE): replace Any with concrete type

        Raises:
            LLMTimeoutError: Request timed out
            LLMRateLimitError: Rate limit exceeded
            LLMAuthenticationError: Authentication failed (invalid credentials)
            LLMContentFilterError: Content blocked by safety filters
            LLMServiceError: Other service errors or retry exhaustion
            TokenBudgetExceededError: Token budget exceeded
        """
        import asyncio

        # Import Phase 1 exceptions
        from src.core.llm.llm_client import (
            LLMAuthenticationError,
            LLMContentFilterError,
            LLMRateLimitError,
            LLMServiceError,
            LLMTimeoutError,
            TokenBudgetExceededError,
        )

        # OTel span for LLM latency visibility (PERF-002 / ADR-014)
        # Span wraps the full token-check + provider call below.
        _otel_tracer = None
        try:
            from src.core.observability.tracing import get_tracer

            _otel_tracer = get_tracer("sanskritisetu.llm")
        except Exception:
            pass

        # Check token budget before generation
        if self.token_budget is not None and self._tokens_used >= self.token_budget:
            logger.warning(
                "Token budget exceeded: used %d, limit %d",
                self._tokens_used,
                self.token_budget,
            )
            raise TokenBudgetExceededError(
                f"Token budget exceeded: {self._tokens_used} >= {self.token_budget}"
            )

        # Provider inference logic based on model name
        if model:
            model_lower = model.lower()
            if "deepseek" in model_lower and LLMProvider.DEEPSEEK in self.providers:
                if provider is None or provider == self.default_provider:
                    provider = LLMProvider.DEEPSEEK
            elif "gemini" in model_lower and LLMProvider.GOOGLE in self.providers:
                if provider is None or provider == self.default_provider:
                    provider = LLMProvider.GOOGLE
            # Add other inference rules here as needed

        provider = provider or self.default_provider

        # If model is not specified, let the provider choose its default or use service default if appropriate
        if model is None:
            if provider == LLMProvider.DEEPSEEK:
                model = "deepseek-chat"
            elif provider == LLMProvider.GOOGLE:
                model = "gemini-2.5-flash"
            else:
                model = self.default_model

        if provider not in self.providers:
            return {
                "content": f"Provider {provider.value} not available. Available providers: {list(self.providers.keys())}",
                "success": False,
                "error": f"Provider {provider.value} not initialized",
            }

        sanitized_prompt, _ = self._gdpr_enforcer.redact_pii(prompt)

        # Phase 1: Retry loop with exponential backoff
        last_error = None
        _span_ctx = (
            _otel_tracer.start_as_current_span(
                "llm.generate_response",
                attributes={
                    "llm.provider": str(provider.value),
                    "llm.model": str(model or "default"),
                },
            )
            if _otel_tracer is not None
            else __import__("contextlib").nullcontext()
        )
        with _span_ctx:
            pass
        for attempt in range(max_retries):
            try:
                # ENHANCEMENT 1: Pass tools and automatic_function_calling to provider
                response = await self.providers[provider].generate_response(
                    prompt=sanitized_prompt,
                    model=model,
                    tools=tools,
                    automatic_function_calling=automatic_function_calling,
                    **kwargs,
                )

                # Add service metadata
                response["service_info"] = {
                    "provider": provider.value,
                    "model": model,
                    "available_providers": [p.value for p in self.providers.keys()],
                    "function_calling_enabled": tools is not None,
                }

                # Update token usage if available in response
                if "usage" in response and isinstance(response["usage"], dict):
                    usage = response["usage"]
                    total_tokens = usage.get("total_tokens", 0)
                    self._tokens_used += total_tokens
                    logger.debug(
                        "Added %d tokens to usage. Total used: %d",
                        total_tokens,
                        self._tokens_used,
                    )

                return cast(dict[str, Any], response)  # TODO(TYPE): replace Any with concrete type

            # Phase 1: Let our custom exceptions pass through directly (no retry)
            except (
                LLMTimeoutError,
                LLMRateLimitError,
                LLMAuthenticationError,
                LLMContentFilterError,
                LLMServiceError,
                TokenBudgetExceededError,
            ):
                raise  # Re-raise our custom exceptions without modification

            except TimeoutError as e:
                # Phase 1: Map standard TimeoutError to LLMTimeoutError (no retry)
                logger.error("LLM request timed out: %s", e)
                raise LLMTimeoutError("Request timed out after 30s") from e

            except (ConnectionError, OSError) as e:
                # Phase 1: Transient errors - retry with exponential backoff
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 0.5 * (2**attempt)
                    logger.warning(
                        "LLM connection error (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        max_retries,
                        wait_time,
                        e,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Exhausted retries
                    logger.error("LLM connection failed after %d retries: %s", max_retries, e)
                    raise LLMServiceError(
                        f"Connection failed after {max_retries} retries: {str(e)}"
                    ) from e

            except Exception as e:
                error_msg = str(e).lower()

                # Phase 1: Detect rate limit errors
                if "rate limit" in error_msg or "429" in error_msg or "quota" in error_msg:
                    logger.error("LLM rate limit exceeded: %s", e)
                    raise LLMRateLimitError("Rate limit exceeded", retry_after=60) from e

                # Phase 1: Detect authentication errors
                if (
                    "auth" in error_msg
                    or "api key" in error_msg
                    or "invalid credential" in error_msg
                    or "401" in error_msg
                    or "403" in error_msg
                ):
                    logger.error("LLM authentication failed: %s", e)
                    raise LLMAuthenticationError("Invalid API key or credentials") from e

                # Phase 1: Detect content filter errors
                if (
                    "content filter" in error_msg
                    or "safety" in error_msg
                    or "blocked" in error_msg
                    or "inappropriate" in error_msg
                ):
                    logger.error("Content blocked by safety system: %s", e)
                    raise LLMContentFilterError("Content blocked by safety system") from e

                # Phase 1: Detect timeout in error message
                if "timeout" in error_msg or "timed out" in error_msg:
                    logger.error("LLM request timed out: %s", e)
                    raise LLMTimeoutError("Request timed out after 30s") from e

                # Generic error fallback
                logger.error("LLM service error: %s", e)
                raise LLMServiceError(f"Service error: {str(e)}") from e

        # Should not reach here, but safety fallback
        if last_error:
            raise LLMServiceError(
                f"Unexpected retry loop exit after {max_retries} retries"
            ) from last_error
        raise LLMServiceError("Unexpected retry loop exit")

    def _sanitize_messages(
        self, messages: list[LLMMessage]
    ) -> tuple[list[LLMMessage], dict[str, str]]:
        """Mask PII in user-role messages; system/assistant pass through unchanged."""
        sanitized: list[LLMMessage] = []
        combined_token_map: dict[str, str] = {}
        offset = 0
        for msg in messages:
            if msg.role == "user":
                masked_content, token_map = self._gdpr_enforcer.redact_pii(msg.content)
                for old_key, value in token_map.items():
                    idx = int(old_key[len("[TOKEN_PII_") : -1])
                    new_key = f"[TOKEN_PII_{idx + offset}]"
                    masked_content = masked_content.replace(old_key, new_key)
                    combined_token_map[new_key] = value
                offset += len(token_map)
                sanitized.append(
                    LLMMessage(role=msg.role, content=masked_content, metadata=msg.metadata)
                )
            else:
                sanitized.append(msg)
        return sanitized, combined_token_map

    @bewaakt_model_aanroep
    async def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[Any],  # TODO(TYPE): replace Any with concrete type
        provider: LLMProvider | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        JSON-mode chat completion using the provider's native structured output.

        Args:
            messages: List of LLMMessage objects (system, user, assistant)
            schema: Pydantic model class describing the expected JSON structure
            provider: LLM provider to use (defaults to self.default_provider)
            model: Model name to use (defaults to self.default_model)
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMResponse with parsed JSON content in .content
        """
        from src.core.llm.llm_client import LLMResponse as LLMResponseType

        provider = provider or self.default_provider

        if provider not in self.providers:
            return LLMResponseType(
                content="",
                model=model or self.default_model,
                provider="unknown",
                success=False,
                error_message=f"Provider {provider.value} not initialized",
            )

        sanitized_messages, token_map = self._sanitize_messages(messages)

        try:
            response = cast(
                LLMResponse,
                await self.providers[provider].complete_json(
                    messages=sanitized_messages,
                    schema=schema,
                    model=model,
                    **kwargs,
                ),
            )
            if token_map:
                response.content = self._gdpr_enforcer.detokenize(response.content, token_map)
            return response
        except Exception as e:
            logger.error("complete_json failed: %s", e)
            return LLMResponseType(
                content="",
                model=model or self.default_model,
                provider=provider.value,
                success=False,
                error_message=str(e),
            )

    @bewaakt_model_aanroep
    async def generate_with_tools(
        self,
        messages: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        tools: list[Any],  # TODO(TYPE): replace Any with concrete type
        temperature: float = 0.3,
        provider: LLMProvider | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate response using Chat API with explicit tool support.
        Bridge for UltimateCVAAgent to accessing providers with tool support.
        """
        provider = provider or self.default_provider

        # Ensure provider is valid
        if provider not in self.providers:
            return {
                "content": f"Provider {provider.value} not available.",
                "success": False,
                "error": f"Provider {provider.value} not initialized",
            }

        # Delegate to generate_response which now supports 'messages' (via update in OllamaProvider)
        # Note: We pass prompt="" because we are providing messages
        return await self.generate_response(
            prompt="",
            provider=provider,
            model=model,
            tools=tools,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )

    async def get_service_status(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get status of all LLM providers"""

        status: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "service": "llm",
            "providers": {},
            "default_provider": self.default_provider.value,
            "default_model": self.default_model,
            "total_providers": len(self.providers),
        }

        for provider_name, provider_instance in self.providers.items():
            try:
                validation = await provider_instance.validate_connection()
                status["providers"][provider_name.value] = validation
            except Exception as e:
                status["providers"][provider_name.value] = {
                    "status": "error",
                    "error": str(e),
                    "available": False,
                }

        return status

    async def test_connectivity(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Test connectivity to all available providers"""

        results: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for provider_name, provider_instance in self.providers.items():
            try:
                test_result = await provider_instance.validate_connection()
                results[provider_name.value] = test_result
            except Exception as e:
                results[provider_name.value] = {
                    "status": "failed",
                    "error": str(e),
                    "available": False,
                }

        return {
            "test_results": results,
            "total_tested": len(results),
            "successful": sum(
                1
                for r in results.values()
                if (isinstance(r, bool) and r)
                or (isinstance(r, dict) and (r.get("available", False) or r.get("status") == "ok"))
            ),
            "failed": sum(
                1
                for r in results.values()
                if (isinstance(r, bool) and not r)
                or (
                    isinstance(r, dict)
                    and (not r.get("available", True) or r.get("status") == "failed")
                )
            ),
        }

    def get_models_info(self) -> list[ModelInfo]:
        """Get rich model information for available models"""
        models_info: list[ModelInfo] = []
        # Capability mapping
        capabilities_map = {
            "gemini-2.5-flash": ["fast", "multimodal", "1M+ context", "latest"],
            "gemini-2.0-flash": ["fast", "multimodal", "efficient"],
            "gemini-2.5-pro": ["reasoning", "multimodal", "2M+ context", "complex-tasks"],
            "gemini-1.5-flash": ["fast", "multimodal", "1M+ context"],
            "gemini-1.5-pro": [
                "reasoning",
                "multimodal",
                "2M+ context",
                "complex-tasks",
            ],
            "deepseek-chat": ["coding", "reasoning", "balanced"],
            "deepseek-reasoner": ["high-reasoning", "math", "cot"],
            "gpt-4-turbo": ["expensive", "reasoning"],
            "llama3.2:3b": ["local", "fast", "private", "offline"],
            "mock-model": ["test", "debug"],
        }

        descriptions_map = {
            "gemini-2.5-flash": "Google's latest fast multimodal model with 1M token context.",
            "gemini-2.0-flash": "Google's efficient multimodal model for high-frequency tasks.",
            "gemini-2.5-pro": "Google's most capable model for complex reasoning and long context.",
            "gemini-1.5-flash": "Google's fast multimodal model for high-frequency tasks.",
            "gemini-1.5-pro": "Google's performing model for complex reasoning and long context.",
            "deepseek-chat": "DeepSeek V3 - Excellent balance of speed and coding performance.",
            "deepseek-reasoner": "DeepSeek R1 - Specialized for complex reasoning and math.",
            "llama3.2:3b": "Local Llama 3.2 model running via Ollama. Private and offline.",
            "mock-model": "Mock provider for testing purposes.",
        }

        for provider_enum, provider_instance in self.providers.items():
            models: list[str] = []
            if hasattr(provider_instance, "model_names"):
                models = provider_instance.model_names
            elif hasattr(provider_instance, "available_models"):
                models = provider_instance.available_models

            for model_name in models:
                # Determine normalized ID
                model_id = model_name

                # Check for existing capability/description else use default
                capabilities = capabilities_map.get(model_name)
                if not capabilities:
                    if "flash" in model_name.lower():
                        capabilities = ["fast", "efficient"]
                    elif "pro" in model_name.lower():
                        capabilities = ["powerful", "reasoning"]
                    elif "reasoner" in model_name.lower():
                        capabilities = ["high-reasoning", "cot"]
                    else:
                        capabilities = ["general"]

                description = descriptions_map.get(model_name)
                if not description:
                    description = f"Modern LLM model ({model_name}) from {provider_enum.value}."

                info = ModelInfo(
                    id=model_id,
                    name=model_name.replace("-", " ")
                    .replace(":", " ")
                    .title()
                    .replace("Gemini", "Google Gemini"),
                    provider=provider_enum.value,
                    capabilities=capabilities,
                    description=description,
                    context_window=1000000 if "gemini" in model_name.lower() else 128000,
                    max_output_tokens=8192,
                )
                models_info.append(info)

        return models_info

    async def get_available_models(self, provider: LLMProvider | None = None) -> list[str]:
        """Get available models for provider"""

        if provider and provider in self.providers:
            return cast(list[str], self.providers[provider].model_names)

        # Return all available models from all providers
        all_models: list[str] = []
        for provider_instance in self.providers.values():
            all_models.extend(provider_instance.model_names)

        return list(set(all_models))  # Remove duplicates

    def is_provider_available(self, provider: LLMProvider) -> bool:
        """Check if provider is available"""
        if provider not in self.providers:
            return False
        return cast(bool, self.providers[provider].initialized)


# Gedeelde instantie voor de applicatie
_llm_service: LLMService | None = None


async def get_llm_service() -> LLMService:
    """Fabrieksfunctie voor de LLM service"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
        if not _llm_service.initialized:
            await _llm_service.initialize()
    return _llm_service
