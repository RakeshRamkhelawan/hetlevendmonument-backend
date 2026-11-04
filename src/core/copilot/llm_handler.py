"""
LLMHandler -- JSON-mode wrapper with 1x retry on validation failure.

Per ADR-027 paragraaf 9:
    - JSON mode is mandatory for all LLM calls that produce actions.
    - Pydantic validation is the final safety net; on parse failure -> 1 retry,
      then the error is propagated to the caller (CopilotService) which
      converts it to a BLOCKED response.

Per CLAUDE.md regel 10: ASCII-only in source code.
Per CLAUDE.md regel 11: structured logging with exc_info on errors.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from pydantic import ValidationError

from src.core.llm.llm_client import LLMClient, LLMMessage
from src.core.copilot.schemas import CopilotAction
from src.core.resilience.circuit_breaker import CircuitBreakerRegistry, CircuitOpenError

logger = logging.getLogger(__name__)


class _JsonAntwoord(Protocol):
    """Wat `LLMHandler` van een antwoord leest; `LLMResponse` en `TenantAntwoord` voldoen allebei."""

    content: str
    success: bool
    error_message: str | None


class JsonModel(Protocol):
    """Een taalmodel dat JSON teruggeeft: een provider of het model van de tenant (`TenantTaalmodel`)."""

    async def complete_json(
        self, messages: list[LLMMessage], schema: type[Any], **kwargs: Any
    ) -> _JsonAntwoord: ...


class LLMProviderError(Exception):
    """LLM provider failure -- raised when all providers fail or raw.success=False."""


class LLMHandler:
    """Handles LLM interaction for a single Co-Pilot turn.

    Supports multi-provider failover with per-provider circuit breakers (ADR-026).
    Primary provider is tried first; on failure, fallback_providers are tried in order.
    Circuit-open providers are skipped without consuming the fallback budget.
    """

    def __init__(
        self,
        provider: JsonModel,
        model_id: str = "onbekend",
        model_version: str = "v3.1",
        fallback_providers: list[JsonModel] | None = None,
        circuit_breaker_registry: CircuitBreakerRegistry | None = None,
    ) -> None:
        self._provider = provider
        self._model_id = model_id
        self._model_version = model_version
        self._fallback_providers: list[JsonModel] = fallback_providers or []
        self._cb_registry: CircuitBreakerRegistry = (
            circuit_breaker_registry or CircuitBreakerRegistry()
        )

    @property
    def model_id(self) -> str:
        # Het model van de tenant staat pas vast na de eerste aanroep; tot dan geldt de opgegeven naam.
        # Zonder dit stond er in elke auditregel "deepseek-chat-v3.1", ook voor een klant op Mistral.
        gekozen = getattr(self._provider, "model_label", None)
        return gekozen if isinstance(gekozen, str) and gekozen else self._model_id

    @property
    def model_version(self) -> str:
        return self._model_version

    async def _call_provider(
        self,
        prov: JsonModel,
        messages: list[LLMMessage],
    ) -> CopilotAction:
        """Call one provider via circuit breaker. Raises LLMProviderError on failure."""
        cb_key = f"{type(prov).__name__}#{self._model_id}"
        cb = await self._cb_registry.get_breaker(cb_key, failure_threshold=3, recovery_timeout=60.0)
        try:
            raw = await cb.execute(prov.complete_json, messages=messages, schema=CopilotAction)
        except CircuitOpenError:
            raise LLMProviderError(f"Circuit open for provider {type(prov).__name__}")
        # SP-H03 guard: check raw.success before model_validate_json
        if not raw.success:
            err_msg = raw.error_message or "unknown error"
            raise LLMProviderError(f"LLM provider failed: {err_msg}. Retry suggested.")
        return CopilotAction.model_validate_json(raw.content)

    async def get_action(
        self,
        message: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        language: str = "nl",
        capabilities: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        retrieval_results: list[dict[str, Any]]
        | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> CopilotAction:
        """Call the LLM with multi-provider failover and per-provider circuit breakers.

        Tries primary provider first, then fallback_providers in order.
        Circuit-open providers are skipped. SP-H03 raw.success guard is enforced.
        On all providers exhausted: raises LLMProviderError.
        """
        system_prompt = self._build_system_prompt(
            language, context, capabilities=capabilities, retrieval_results=retrieval_results
        )
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=message),
        ]

        all_providers = [self._provider] + self._fallback_providers
        last_error: Exception | None = None

        for prov in all_providers:
            try:
                return await self._call_provider(prov, messages)
            except LLMProviderError as exc:
                logger.warning(
                    "llm_handler.provider_failed provider=%s error=%s -- trying next",
                    type(prov).__name__,
                    exc,
                    extra={"model_id": self._model_id},
                )
                last_error = exc
                continue
            except ValidationError as first_error:
                logger.warning(
                    "llm_handler.json_invalid retrying once provider=%s",
                    type(prov).__name__,
                    extra={
                        "model_id": self._model_id,
                        "language": language,
                        "error": str(first_error),
                    },
                )
                retry_system = (
                    system_prompt + "\n\nYour previous output was invalid JSON. "
                    "Output strictly valid JSON matching the schema. "
                    "Do not include any prose, markdown, or commentary."
                )
                retry_messages = [
                    LLMMessage(role="system", content=retry_system),
                    LLMMessage(role="user", content=message),
                ]
                raw = await prov.complete_json(
                    messages=retry_messages,
                    schema=CopilotAction,
                )
                # SP-H03 guard on retry raw.success
                if not raw.success:
                    last_error = LLMProviderError(
                        f"LLM retry failed: {raw.error_message or 'unknown'}"
                    )
                    continue
                return CopilotAction.model_validate_json(raw.content)

        if last_error is not None:
            raise last_error
        raise LLMProviderError("All LLM providers exhausted.")

    def _build_system_prompt(
        self,
        language: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        capabilities: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        retrieval_results: list[dict[str, Any]]
        | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        schema_str = json.dumps(CopilotAction.model_json_schema(), indent=2)
        # Validate language to prevent prompt injection
        safe_language = language if language in ("nl", "en") else "en"
        context_key_count = len(context) if isinstance(context, dict) else 0

        prompt = (
            "You are a helpful AI assistant. Respond in the user's language.\n"
            f"Language: {safe_language}\n\n"
            "You must output strictly valid JSON matching this schema:\n"
            f"{schema_str}\n\n"
        )
        if context_key_count:
            prompt += (
                f"{context_key_count} context item(s) are available "
                "(do NOT include them in output).\n"
            )

        def _sanitize_prompt_input(text: str, max_len: int = 200) -> str:
            """Strip common prompt injection patterns and cap length."""
            if not isinstance(text, str):
                text = str(text)
            # Strip common injection markers
            for marker in (
                "Ignore previous",
                "ignore previous",
                "system:",
                "System:",
                "===",
                "```",
                "<|",
                "|>",
                "[INST",
                "[/INST",
            ):
                text = text.replace(marker, "")
            return text[:max_len]

        # CRITICAL-3: inject platform capability catalog
        # Security: tool metadata is controlled by platform, but sanitize defensively
        if capabilities:
            tools = capabilities.get("tools", [])
            if tools:
                prompt += "\n=== AVAILABLE TOOLS ===\n"
                for idx, tool in enumerate(tools, 1):
                    name = _sanitize_prompt_input(tool.get("name", "unknown"), max_len=64)
                    desc = _sanitize_prompt_input(tool.get("description", ""), max_len=200)
                    prompt += f"{idx}. {name}: {desc}\n"
                prompt += "=== END TOOLS ===\n"

        # HIGH-4: inject retrieval results
        # Security: retrieval content may be user-controlled; sanitize strictly
        if retrieval_results:
            prompt += "\n=== RETRIEVED CONTEXT ===\n"
            for idx, doc in enumerate(retrieval_results, 1):
                title = _sanitize_prompt_input(doc.get("title", f"Doc {idx}"), max_len=100)
                content = _sanitize_prompt_input(doc.get("content", ""), max_len=500)
                prompt += f"[{idx}] {title}: {content}\n"
            prompt += "=== END RETRIEVED CONTEXT ===\n"

        prompt += (
            "\nRules:\n"
            "- message: natural language response to the user\n"
            "- action: tool name or null\n"
            "- action_params: dictionary of parameters for the tool\n"
            "- confidence: float 0.0-1.0\n"
            "- reasoning: brief explanation of your decision\n"
            "- No extra fields. No markdown. No commentary outside JSON.\n"
        )
        return prompt
