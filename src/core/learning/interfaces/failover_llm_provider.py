"""
FailoverLLMProvider -- LLM provider met failover chain en circuit breaker.

Probeert providers in volgorde totdat er een succesvolle response is.
Een provider waarvan het circuit open is, wordt overgeslagen totdat de
recovery timeout (standaard 60s) verloopt.

Gebruik:
    chain = FailoverLLMProvider([
        ClaudeSuggestionProvider(api_key="..."),
        GeminiSuggestionProvider(api_key="..."),
        MockSuggestionProvider(),
    ])
    suggestion = await chain.suggest(context, profile)
"""

from typing import Any

from loguru import logger

from src.core.learning.interfaces.llm_provider import ILLMSuggestionProvider, TokenUsage
from src.core.learning.metrics import (
    record_twin_llm_provider_circuit_open,
    record_twin_llm_provider_failure,
)
from src.core.learning.safety.output_sanitizer import OutputSanitizer
from src.core.resilience.circuit_breaker import CircuitBreakerRegistry, CircuitOpenError

_LLM_FAILURE_THRESHOLD = 3
_LLM_RECOVERY_TIMEOUT = 60.0


class FailoverLLMProvider:
    """
    LLM provider die een chain van providers probeert met circuit breaker bescherming.

    Per provider wordt een aparte circuit breaker bijgehouden. Na 3 opeenvolgende
    failures gaat het circuit OPEN en wordt de provider 60 seconden overgeslagen.

    Args:
        providers: Lijst van ILLMSuggestionProvider implementaties.
                   Geprobeerd in volgorde totdat er een niet-lege
                   response is of alle providers faalden/open zijn.
    """

    def __init__(self, providers: list[ILLMSuggestionProvider]) -> None:
        self._providers = providers
        self._last_token_usage = TokenUsage()
        self._registry = CircuitBreakerRegistry()

    async def suggest(
        self,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        user_profile: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """
        Genereer een suggestie via de eerste beschikbare provider in de chain.

        Providers waarvan het circuit OPEN is worden overgeslagen. Na recovery
        timeout worden ze opnieuw geprobeerd (HALF_OPEN state).

        Returns:
            Suggestietekst, of lege string als alle providers faalden of open zijn.
        """
        last_error: Exception | None = None

        for idx, provider in enumerate(self._providers):
            provider_name = type(provider).__name__
            # Key includes index so two providers of the same type have independent breakers
            breaker_key = f"{provider_name}#{idx}"
            cb = await self._registry.get_breaker(
                breaker_key,
                failure_threshold=_LLM_FAILURE_THRESHOLD,
                recovery_timeout=_LLM_RECOVERY_TIMEOUT,
            )

            try:
                result = await cb.execute(provider.suggest, context, user_profile)
                if result:
                    self._last_token_usage = provider.get_last_token_usage()
                    # Sanitize PII and credential leaks before returning (ADR-026 S.2.4)
                    cleaned, violations = OutputSanitizer.clean(result)
                    if violations:
                        logger.warning(
                            "llm_output_sanitized",
                            provider_type=provider_name,
                            violation_types=sorted(set(violations)),
                        )
                    if idx > 0:
                        logger.info(
                            "llm_failover_success",
                            provider_index=idx,
                            provider_type=provider_name,
                            suggestion_length=len(cleaned),
                        )
                    return cleaned
            except CircuitOpenError:
                logger.warning(
                    "llm_circuit_open_skipping_provider",
                    provider_index=idx,
                    provider_type=provider_name,
                )
                record_twin_llm_provider_circuit_open(provider_name)
                continue
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "llm_failover_attempt_failed",
                    provider_index=idx,
                    provider_type=provider_name,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                record_twin_llm_provider_failure(provider_name)

        logger.error(
            "llm_failover_all_providers_failed",
            provider_count=len(self._providers),
            last_error_type=type(last_error).__name__ if last_error else None,
            last_error=str(last_error) if last_error else None,
        )
        return ""

    @property
    def provider_count(self) -> int:
        """Aantal providers in de chain."""
        return len(self._providers)

    @property
    def provider_names(self) -> list[str]:
        """Namen van providers in de chain (voor monitoring)."""
        return [type(p).__name__ for p in self._providers]

    @property
    def last_token_usage(self) -> TokenUsage:
        """Token usage from the last successful suggest() call."""
        return self._last_token_usage

    async def get_circuit_states(self) -> dict[str, str]:
        """Huidige circuit breaker states per provider (voor monitoring/diagnostics).

        Async omadat de registry een async lock gebruikt voor thread-safe toegang.
        """
        all_states = await self._registry.get_all_states()
        return {name: state["state"].lower() for name, state in all_states.items()}
