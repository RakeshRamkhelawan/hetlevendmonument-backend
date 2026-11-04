"""
LLM Fallback Chain - Robust LLM calls with multiple fallback levels.

Provides:
- Tiered fallback: Primary -> Secondary -> Local -> Heuristic
- Automatic failover on timeout/error
- Cost-aware model selection
- Local model support (Ollama, LM Studio)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict, TypeVar, cast
from collections.abc import Callable

from pydantic import BaseModel
from src.core.shared.model_deur import bewaakt_model_aanroep
from src.core.shared.tenant_llm_keuze import TOEGESTANE_KEUZES, provider_mag_voor_keuze
from src.core.resilience.circuit_breaker import CircuitBreakerRegistry, CircuitOpenError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class _StatsDict(TypedDict):
    """Internal stats tracked by LLMFallbackChain."""

    total_calls: int
    successful_calls: int
    fallback_count: int
    tier_usage: dict[str, int]


class ModelTier(Enum):
    """LLM tiers ordered by preference/cost."""

    PRIMARY = "primary"  # Best quality (e.g., GPT-4, Claude-3)
    SECONDARY = "secondary"  # Good quality, lower cost (e.g., GPT-3.5)
    LOCAL = "local"  # On-premise (Ollama, LM Studio)
    HEURISTIC = "heuristic"  # Rule-based fallback


@dataclass
class ModelConfig:
    """Configuration for an LLM model."""

    name: str
    tier: ModelTier
    provider: str  # "openai", "anthropic", "google", "ollama", "lmstudio"
    timeout_seconds: float = 30.0
    max_retries: int = 2
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    context_window: int = 8192
    supports_json_mode: bool = False
    base_url: str | None = None  # For local models
    api_key_env: str | None = None


@dataclass
class FallbackResult:
    """Result from fallback chain execution."""

    success: bool
    content: str | None
    model_used: str
    tier_used: ModelTier
    latency_ms: float
    attempts: int
    errors: list[str] = field(default_factory=list)
    token_usage: dict[str, int] | None = None
    estimated_cost_usd: float = 0.0


class LLMFallbackChain:
    """
    Manages LLM calls with automatic fallback to cheaper/local models.

    Usage:
        chain = LLMFallbackChain()
        chain.register_model(ModelConfig("gpt-4", ModelTier.PRIMARY, "openai"))
        chain.register_model(ModelConfig("llama2", ModelTier.LOCAL, "ollama", base_url="http://localhost:11434"))

        result = await chain.generate(
            prompt="Explain quantum computing",
            response_model=Explanation,
            fallback=True,
        )
    """

    def __init__(self, max_fallbacks: int = 3) -> None:
        self.max_fallbacks = max_fallbacks
        self._models: dict[ModelTier, list[ModelConfig]] = {tier: [] for tier in ModelTier}
        self._providers: dict[
            str, Any  # TODO(TYPE): replace Any with concrete type
        ] = {}  # TODO(TYPE): Any -- provider instances are polymorphic (OpenAI/Gemini/Ollama clients)
        self._stats: _StatsDict = {
            "total_calls": 0,
            "successful_calls": 0,
            "fallback_count": 0,
            "tier_usage": {tier.value: 0 for tier in ModelTier},
        }
        self._cb_registry = CircuitBreakerRegistry()

    def register_model(self, config: ModelConfig) -> None:
        """Register a model configuration."""
        self._models[config.tier].append(config)
        logger.info(f"Registered model {config.name} ({config.tier.value})")

    def register_provider(
        self, name: str, provider: Any  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register a provider client (OpenAI, Anthropic, etc.)."""
        self._providers[name] = provider
        logger.info(f"Registered provider: {name}")

    @bewaakt_model_aanroep
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        response_model: type | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        fallback: bool = True,
        preferred_tier: ModelTier | None = None,
        timeout: float | None = None,
        tenant_keuze: str | None = None,
    ) -> FallbackResult:
        """
        Generate text with automatic fallback.

        Args:
            prompt: The user prompt
            system_prompt: System instructions
            response_model: Pydantic model for structured output
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            fallback: Whether to try fallback models on failure
            preferred_tier: Start from this tier (default: PRIMARY)
            timeout: Override default timeout
            tenant_keuze: De taalmodelkeuze van de klant voor wie dit verzoek is (`mistral` of
                `ollama`, zie `tenant_llm_keuze`). Bij een waarde worden ALLEEN de modellen
                aangeroepen die bij die keuze horen: nooit DeepSeek, nooit een ander gehuurd
                model, en een klant die `ollama` koos valt bij een storing NIET door naar een
                gehuurd model maar krijgt een mislukt resultaat met de reden. Een onbekende
                keuze weigert het verzoek. Zonder waarde (platformeigen aanroepen zonder
                klantgegevens) gedraagt de keten zich als voorheen.

        Returns:
            FallbackResult with content and metadata
        """
        start_time = time.time()
        self._stats["total_calls"] += 1

        if tenant_keuze is not None and tenant_keuze not in TOEGESTANE_KEUZES:
            return FallbackResult(
                success=False,
                content=None,
                model_used="none",
                tier_used=ModelTier.HEURISTIC,
                latency_ms=(time.time() - start_time) * 1000,
                attempts=0,
                errors=[f"Onbekende taalmodelkeuze {tenant_keuze!r}; het verzoek is niet verstuurd"],
            )

        # Determine tier order
        tiers_to_try = self._get_tier_order(preferred_tier)

        errors: list[str] = []
        attempts = 0

        for tier in tiers_to_try:
            if attempts >= self.max_fallbacks:
                break

            for model_config in self._models[tier]:
                if attempts >= self.max_fallbacks:
                    break

                # Een tenantverzoek gaat alleen naar de providers die bij zijn keuze horen. Overslaan
                # is bewust geen poging: de rest van de keten loopt gewoon door.
                if tenant_keuze is not None and not provider_mag_voor_keuze(
                    model_config.provider, tenant_keuze
                ):
                    logger.info(
                        "llm_keten_slaat_over: %s (provider %s niet toegestaan voor keuze %s)",
                        model_config.name,
                        model_config.provider,
                        tenant_keuze,
                    )
                    continue

                # Circuit breaker check: OPEN providers are skipped without
                # consuming the fallback budget (B-008 fix, ADR-026).
                cb_key = f"{model_config.provider}#{model_config.name}"
                cb = await self._cb_registry.get_breaker(
                    cb_key, failure_threshold=3, recovery_timeout=60.0
                )

                try:
                    result = await cb.execute(
                        self._call_model,
                        model_config=model_config,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        response_model=response_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout or model_config.timeout_seconds,
                    )

                    # attempts only increments for real calls (not circuit-open skips)
                    attempts += 1

                    if result is not None:
                        latency_ms = (time.time() - start_time) * 1000
                        self._stats["successful_calls"] += 1
                        self._stats["tier_usage"][tier.value] += 1

                        if attempts > 1:
                            self._stats["fallback_count"] += 1

                        cost = self._estimate_cost(result, model_config)

                        return FallbackResult(
                            success=True,
                            content=result if isinstance(result, str) else str(result),
                            model_used=model_config.name,
                            tier_used=tier,
                            latency_ms=latency_ms,
                            attempts=attempts,
                            errors=errors,
                            estimated_cost_usd=cost,
                        )

                except CircuitOpenError:
                    # Provider circuit is OPEN -- skip silently, do not count as attempt
                    logger.info("llm_circuit_open_skipping: %s", cb_key)
                    continue

                except TimeoutError:
                    attempts += 1
                    errors.append(f"{model_config.name}: timeout")
                    logger.warning("Model %s timed out", model_config.name)

                except Exception as e:
                    attempts += 1
                    errors.append(f"{model_config.name}: {str(e)}")
                    logger.warning("Model %s failed: %s", model_config.name, e)

                if not fallback:
                    break

            if not fallback:
                break

        # All models failed
        if tenant_keuze is not None and attempts == 0:
            errors.append(
                f"Geen toegestaan taalmodel beschikbaar voor de keuze '{tenant_keuze}'; er is "
                "bewust niet teruggevallen op een ander model"
            )
        latency_ms = (time.time() - start_time) * 1000
        return FallbackResult(
            success=False,
            content=None,
            model_used="none",
            tier_used=ModelTier.HEURISTIC,
            latency_ms=latency_ms,
            attempts=attempts,
            errors=errors,
        )

    def _get_tier_order(self, preferred: ModelTier | None) -> list[ModelTier]:
        """Get tier order starting from preferred."""
        tiers = list(ModelTier)
        if preferred:
            # Move preferred to front
            tiers.remove(preferred)
            tiers.insert(0, preferred)
        return tiers

    async def _call_model(
        self,
        model_config: ModelConfig,
        prompt: str,
        system_prompt: str | None,
        response_model: type | None,
        temperature: float,
        max_tokens: int | None,
        timeout: float,
    ) -> str | None:
        """Call specific model with timeout."""

        if model_config.provider == "ollama":
            return await self._call_ollama(
                model_config, prompt, system_prompt, temperature, max_tokens, timeout
            )
        elif model_config.provider == "lmstudio":
            return await self._call_lmstudio(
                model_config, prompt, system_prompt, temperature, max_tokens, timeout
            )
        elif model_config.provider == "openai":
            return await self._call_openai(
                model_config,
                prompt,
                system_prompt,
                response_model,
                temperature,
                max_tokens,
                timeout,
            )
        elif model_config.provider == "google":
            return await self._call_google(
                model_config, prompt, system_prompt, temperature, max_tokens, timeout
            )
        elif model_config.provider == "deepseek":
            raise ValueError(
                "DeepSeek (China, geen verwerkersovereenkomst) mag niet met klantgegevens (ADR-041 B14)"
            )
        elif model_config.provider == "mistral":
            return await self._call_mistral(
                model_config, prompt, system_prompt, response_model, temperature, max_tokens, timeout
            )
        else:
            raise ValueError(f"Unknown provider: {model_config.provider}")

    async def _call_ollama(
        self,
        config: ModelConfig,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int | None,
        timeout: float,
    ) -> str:
        """Call Ollama local model."""
        import aiohttp

        base_url = config.base_url or "http://localhost:11434"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/api/generate",
                json={
                    "model": config.name,
                    "prompt": prompt,
                    "system": system_prompt or "",
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens or 1024,
                    },
                },
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status != 200:
                    raise Exception(f"Ollama error: {response.status}")

                data: dict[
                    str, Any  # TODO(TYPE): replace Any with concrete type
                ] = await response.json()  # TODO(TYPE): replace Any with concrete type
                return str(data.get("response", ""))

    async def _call_lmstudio(
        self,
        config: ModelConfig,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int | None,
        timeout: float,
    ) -> str:
        """Call LM Studio local model."""
        import aiohttp

        base_url = config.base_url or "http://localhost:1234"

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/v1/chat/completions",
                json={
                    "model": config.name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens or 1024,
                },
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status != 200:
                    raise Exception(f"LM Studio error: {response.status}")

                data: dict[
                    str, Any  # TODO(TYPE): replace Any with concrete type
                ] = await response.json()  # TODO(TYPE): replace Any with concrete type
                return str(data["choices"][0]["message"]["content"])

    async def _call_openai(
        self,
        config: ModelConfig,
        prompt: str,
        system_prompt: str | None,
        response_model: type | None,
        temperature: float,
        max_tokens: int | None,
        timeout: float,
    ) -> str:
        """Call OpenAI API."""
        try:
            import openai
        except ImportError:
            raise ImportError("openai package required for OpenAI provider")

        client = self._providers.get("openai") or openai.AsyncOpenAI()

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[
            str, Any  # TODO(TYPE): replace Any with concrete type
        ] = {  # NOTE: openai accepts heterogeneous kwargs (model, messages, temperature, response_format)
            "model": config.name,
            "messages": messages,
            "temperature": temperature,
            "timeout": timeout,
        }

        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        if response_model and config.supports_json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        return str(content) if content is not None else ""

    async def _call_google(
        self,
        config: ModelConfig,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int | None,
        timeout: float,
    ) -> str:
        """Call Google GenAI API using new google-genai SDK."""
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError:
            raise ImportError("google-genai package required: pip install google-genai")

        import os

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")

        if "google" not in self._providers:
            self._providers["google"] = genai.Client(api_key=api_key)

        client = self._providers["google"]
        content = prompt
        if system_prompt:
            content = f"{system_prompt}\n\n{prompt}"

        response = await client.aio.models.generate_content(
            model=config.name,
            contents=content,
            config=genai_types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens or 1024,
            ),
        )

        return response.text or ""

    async def _call_mistral(
        self,
        config: ModelConfig,
        prompt: str,
        system_prompt: str | None,
        response_model: type | None,
        temperature: float,
        max_tokens: int | None,
        timeout: float,
    ) -> str:
        """Mistral (EU) via `MistralProvider`; de sleutel komt uit `MISTRAL_API_KEY` en blijft daar."""
        from src.core.llm.llm_client import LLMMessage
        from src.core.llm.mistral_provider import MistralProvider

        provider = MistralProvider()
        berichten = []
        if system_prompt:
            berichten.append(LLMMessage(role="system", content=system_prompt))
        berichten.append(LLMMessage(role="user", content=prompt))
        extra: dict[str, object] = {
            "model": config.name,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
        }
        if response_model and config.supports_json_mode:
            extra["response_format"] = {"type": "json_object"}
        antwoord = await asyncio.wait_for(provider.chat_completion(berichten, **extra), timeout)
        if not antwoord.success:
            raise RuntimeError(antwoord.error_message or "Mistral gaf geen antwoord")
        return antwoord.content

    def _estimate_cost(self, result: str, config: ModelConfig) -> float:
        """Estimate API call cost."""
        output_tokens = len(result.split()) * 1.3  # Rough estimate
        input_tokens = config.context_window * 0.5  # Assume half context used

        cost = (input_tokens / 1000) * config.cost_per_1k_input + (
            output_tokens / 1000
        ) * config.cost_per_1k_output
        return round(cost, 6)

    async def get_circuit_states(
        self,
    ) -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Return current circuit breaker states per provider+model key.

        # NOTE: inner dict mirrors CircuitBreaker.get_state() schema (state, metrics)
        """
        return await self._cb_registry.get_all_states()

    def get_stats(self) -> dict[str, object]:
        """Get usage statistics."""
        total_int: int = self._stats["total_calls"]
        success_int: int = self._stats["successful_calls"]
        fallback_int: int = self._stats["fallback_count"]

        return {
            **self._stats,
            "success_rate": success_int / total_int if total_int > 0 else 0.0,
            "average_fallbacks": fallback_int / total_int if total_int > 0 else 0.0,
        }

    def reset_stats(self) -> None:
        """Reset usage statistics."""
        self._stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "fallback_count": 0,
            "tier_usage": {tier.value: 0 for tier in ModelTier},
        }


# Global fallback chain instance
_default_chain: LLMFallbackChain | None = None


def get_fallback_chain() -> LLMFallbackChain:
    """Get or create default fallback chain."""
    global _default_chain
    if _default_chain is None:
        _default_chain = LLMFallbackChain()

        # Register default models if env vars present
        import os

        # Mistral (EU) is het gehuurde standaardmodel (ADR-041 B14, besluit Rakesh 2026-10-15) en
        # staat daarom VOORAAN: binnen een tier wordt in registratievolgorde geprobeerd, dus een
        # Google- of OpenAI-sleutel mag klantprompts niet voor Mistral krijgen (Gate 2, 2026-10-19).
        if os.getenv("MISTRAL_API_KEY"):
            _default_chain.register_model(
                ModelConfig(
                    name=os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
                    tier=ModelTier.PRIMARY,
                    provider="mistral",
                    supports_json_mode=True,
                    context_window=32000,
                    api_key_env="MISTRAL_API_KEY",
                )
            )

        if os.getenv("OPENAI_API_KEY"):
            _default_chain.register_model(
                ModelConfig(
                    name="gpt-3.5-turbo",
                    tier=ModelTier.SECONDARY,
                    provider="openai",
                    cost_per_1k_input=0.0015,
                    cost_per_1k_output=0.002,
                    supports_json_mode=True,
                )
            )

        if os.getenv("GOOGLE_API_KEY"):
            _default_chain.register_model(
                ModelConfig(
                    name="gemini-2.5-pro",
                    tier=ModelTier.PRIMARY,
                    provider="google",
                    cost_per_1k_input=0.00005,
                    cost_per_1k_output=0.0002,
                )
            )

        # DeepSeek staat hier NIET meer, ook niet bij een gezette `DEEPSEEK_API_KEY`: deze keten
        # verwerkt promptteksten uit klanttaken (routering, planning), en DeepSeek (China, geen
        # verwerkersovereenkomst) mag niet met klantgegevens (ADR-041 B14). Een zelf aangesloten
        # DeepSeekmodel wordt in `_call_model` geweigerd.

        # Always try local models
        _default_chain.register_model(
            ModelConfig(
                name="llama3.2",
                tier=ModelTier.LOCAL,
                provider="ollama",
                base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
            )
        )

        _default_chain.register_model(
            ModelConfig(
                name="local-model",
                tier=ModelTier.LOCAL,
                provider="lmstudio",
                base_url=os.getenv("LMSTUDIO_URL", "http://localhost:1234"),
            )
        )

    return _default_chain
