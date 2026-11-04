"""Mistral AI (Frankrijk, EU) in de provider-stapel van de agenten (`LLMService`).

Mistral spreekt het OpenAI-chatprotocol, dus dit is `OpenAICompatibleProvider` met twee vaste punten:
het EU-eindpunt als standaardadres en `MISTRAL_API_KEY` als sleutel. De klasse zet het etiket
`mistral` zelf (via `PROVIDER_LABEL`), zodat `provider_name` en `serves_mock` van de basisklasse
ongewijzigd blijven gelden.

**Geen sleutel is een FOUT, geen stille terugval.** `ValueError` bij het bouwen, zodat de aanroeper het
ziet. `LLMService.for_tenant` bouwt deze klasse BUITEN de try/except van `LLMService.__init__` om,
want die zou een `ValueError` buiten productie omzetten in een namaakmodel (ADR-041 B14).
"""

from __future__ import annotations

import os

from src.core.services.llm.base import LLMConfig
from src.core.services.llm.providers.openai_compatible import (
    PROVIDER_LABEL,
    OpenAICompatibleProvider,
)

STANDAARD_BASIS_URL = "https://api.mistral.ai/v1"
STANDAARD_MODEL = "mistral-small-latest"


def gekozen_model() -> str:
    """`LLM_MODEL` telt alleen als `LLM_PROVIDER=mistral`; een DeepSeek-naam telt nooit."""
    if os.getenv("LLM_PROVIDER", "").strip().lower() == "mistral":
        naam = os.getenv("LLM_MODEL", "").strip()
        if naam and "deepseek" not in naam.lower():
            return naam
    return STANDAARD_MODEL


class MistralProvider(OpenAICompatibleProvider):
    """Mistral chat completions via het generieke OpenAI-compatibele pad."""

    def __init__(self, config: LLMConfig) -> None:
        if not config.base_url:
            config.base_url = os.getenv("MISTRAL_BASE_URL", STANDAARD_BASIS_URL)
        if not config.api_key:
            config.api_key = os.getenv("MISTRAL_API_KEY") or None
        if not config.model:
            config.model = gekozen_model()
        if not config.base_url.lower().startswith("https://"):
            # De sleutel gaat als bearer mee; naar een onbeveiligd adres zou hij leesbaar over het net gaan.
            raise ValueError("MISTRAL_BASE_URL moet een https-adres zijn")
        config.extra_params = {**(config.extra_params or {}), PROVIDER_LABEL: "mistral"}
        super().__init__(config)

    def _validate_config(self) -> None:
        if not self.config.api_key:
            raise ValueError(
                "MISTRAL_API_KEY is niet gezet: zonder sleutel kan Mistral niet worden aangeroepen, "
                "en er wordt bewust niet teruggevallen op een ander of een namaakmodel"
            )
        super()._validate_config()
