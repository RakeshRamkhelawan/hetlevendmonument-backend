"""
Mock LLM Provider - Demo/fallback provider when no real LLM is configured.

Returns helpful placeholder responses. Replace with a real provider
(deepseek, gemini, ollama) by setting LLM_PROVIDER + LLM_MODEL env vars.
"""

import logging
from typing import Optional

from src.core.services.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
)

logger = logging.getLogger(__name__)


class MockProvider(LLMProvider): # LLMProvider untyped without mypy plugin
    """
    Mock LLM provider for demo/development use.

    No external service required. Returns a canned response that
    acknowledges the user's message and explains the system is in
    demo mode.
    """

    def _validate_config(self) -> None:
        if not self.config.model:
            self.config.model = "mock-model"
        logger.info("MockProvider initialized (no real LLM configured)")

    async def generate(
        self,
        messages: list[LLMMessage],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        last_user_content = ""
        for msg in reversed(messages):
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "")
            if role == "user":
                last_user_content = (
                    msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
                ) or ""
                break

        preview = last_user_content[:80].strip()
        ellipsis = "..." if len(last_user_content) > 80 else ""

        response_text = (
            f'Ik heb uw vraag ontvangen: "{preview}{ellipsis}"\n\n'
            "Op dit moment draait de CVA-assistent in demo-modus omdat er nog geen "
            "AI-provider is geconfigureerd. Zodra de DeepSeek API-sleutel is ingesteld "
            "in de productieomgeving, ontvangt u hier echte AI-antwoorden.\n\n"
            "Neem contact op met de beheerder om de LLM-provider te activeren."
        )

        tokens = len(response_text.split())
        return LLMResponse(
            content=response_text,
            prompt_tokens=len(last_user_content.split()),
            completion_tokens=tokens,
            total_tokens=len(last_user_content.split()) + tokens,
            model=self.config.model,
            finish_reason="stop",
        )

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def serves_mock(self) -> bool:
        """Altijd. Dit IS het namaakmodel.

        Expliciet en niet via de standaard in `LLMProvider`, ook al geeft die hier toevallig
        hetzelfde antwoord. De standaard leidt af uit `provider_name`, en deze klasse bepaalt
        die naam zelf -- dan hangt een veiligheidsbeslissing aan een tekst in plaats van aan
        wat de klasse doet. Bewaakt door
        `tests/architecture/test_een_provider_die_zijn_naam_kiest_kiest_ook_serves_mock.py`,
        die deze klasse op 2026-09-21 als eerste betrapte.
        """
        return True

    @property
    def supports_streaming(self) -> bool:
        return False
