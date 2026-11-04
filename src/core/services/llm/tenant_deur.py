"""De ENE deur naar het taalmodel voor alles wat tenantgegevens verwerkt (ADR-041 B14, brief 2026-10-19).

**Het probleem dat dit sluit.** Naast `LLMService.for_tenant` bouwde elke dienst zijn eigen client met een
eigen leverancier: een harde `DeepSeekProvider()` in de routering, een module-level client naar
api.deepseek.com in de focus-generator, een eigen Gemini/DeepSeek/Qwen-keuze in de workflowgenerator en de
focussuggesties, een DeepSeek-terugval in `LocalClient`. Daarmee gingen klantgegevens naar een leverancier
die de klant niet koos, ook met een Mistralsleutel in de omgeving.

**De regel.** Een dienst of agent die een tenantverzoek afhandelt, vraagt zijn taalmodel HIER:
`TenantTaalmodel(tenant_id)`. Dat is de keuze van de klant (`LLMService.for_tenant`: zijn eigen eindpunten,
anders `tenants.settings["llm_provider"]`, standaard Mistral). Zonder tenant (`None`: systeemtaken zonder
klantgegevens) is het de platformstandaard, en die is Mistral.

**Geen stille terugval.** Een storing geeft een fout: `tekst` laat de uitzondering door; `generate_response`
en `chat_completion` (de vormen die bestaande aanroepers lezen) melden `success=False` met de reden. Er
komt nooit een succesantwoord van een ander model dan het gekozen model, en geen namaakmodel.

Bewaakt door `tests/unit/llm/test_tenant_deur.py` en `tests/architecture/test_geen_deepseek_voor_klantgegevens.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, TypedDict

from src.core.shared.model_deur import bewaakt_model_aanroep
from src.core.services.llm.base import LLMMessage
from src.core.services.llm.service import LLMService
from src.core.shared.tenant_llm_keuze import TenantLLMNietBeschikbaarError

logger = logging.getLogger(__name__)


class _Bericht(Protocol):
    """Wat een bericht moet hebben, ongeacht uit welke clientbibliotheek het komt."""

    @property
    def role(self) -> str: ...

    @property
    def content(self) -> str: ...


class TaalmodelAntwoord(TypedDict, total=False):
    """Het woordenboek van `generate_response`; `success` is er altijd, de rest hangt van de uitkomst af."""

    success: bool
    content: str
    text: str
    model: str
    provider: str
    error: str


@dataclass
class TenantAntwoord:
    """Het antwoord in de vorm die `chat_completion`-aanroepers lezen (`.content`, `.success`)."""

    content: str
    success: bool = True
    model: str = ""
    provider: str = ""
    error_message: str | None = None


@dataclass(frozen=True)
class _Verwerker:
    """`default_provider` zoals stapel A hem gaf: een object met `.value`."""

    value: str


class TenantTaalmodel:
    """Het taalmodel van EEN tenant (of de platformstandaard bij `tenant_id=None`)."""

    def __init__(self, tenant_id: int | None) -> None:
        self.tenant_id = tenant_id
        #: Voor de noodstop (zie `noodstop/model_deur.py`): deze deur kent zijn klant zelf.
        self.noodstop_tenant_id = tenant_id
        self._service: LLMService | None = None
        #: "provider:model" van het gekozen model, gevuld zodra het is opgevraagd (voor een auditregel).
        self.model_label: str | None = None
        #: De verwerker, in de vorm die stapel A aanbood (`.value`); `tenant` tot het model is opgevraagd.
        self.default_provider: _Verwerker = _Verwerker("tenant")

    async def _dienst(self) -> LLMService:
        """De `LLMService` van deze tenant; een keer opgevraagd per deur."""
        if self._service is None:
            if self.tenant_id is None:
                self._service = _platformstandaard()
            else:
                self._service = await LLMService.for_tenant(self.tenant_id)
            self.model_label = (
                f"{self._service.provider.provider_name}:{self._service.provider.config.model}"
            )
            self.default_provider = _Verwerker(self._service.provider.provider_name)
        return self._service

    @bewaakt_model_aanroep
    async def tekst(
        self,
        prompt: str,
        *,
        systeem: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Een antwoord als tekst. Een storing komt als uitzondering bij de aanroeper."""
        berichten: list[LLMMessage] = []
        if systeem:
            berichten.append(LLMMessage(role="system", content=systeem))
        berichten.append(LLMMessage(role="user", content=prompt))
        dienst = await self._dienst()
        # `LLMService.generate` geeft de TEKST terug. Bewust zonder `tenant_id`: de semantische cache is
        # per tenant en hoort bij de aanroepen die haar nodig hebben, niet bij elke deuraanroep.
        antwoord = await dienst.generate(berichten, temperature=temperature, max_tokens=max_tokens)
        return str(antwoord)

    @bewaakt_model_aanroep
    async def tekst_met_gebruik(
        self,
        prompt: str,
        *,
        systeem: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, int, int]:
        """Het antwoord met de gebruikte invoer- en uitvoertokens (voor een kostenregistratie)."""
        berichten: list[LLMMessage] = []
        if systeem:
            berichten.append(LLMMessage(role="system", content=systeem))
        berichten.append(LLMMessage(role="user", content=prompt))
        dienst = await self._dienst()
        uitkomst = await dienst.generate(
            berichten, temperature=temperature, max_tokens=max_tokens, return_usage=True
        )
        if isinstance(uitkomst, tuple):
            tekst, gebruik = uitkomst
            return (
                str(tekst),
                _geheel(gebruik.get("prompt_tokens")) or 0,
                _geheel(gebruik.get("completion_tokens")) or 0,
            )
        return str(uitkomst), 0, 0

    async def provider_naam(self) -> str:
        """Welke verwerker het gekozen model is (voor een antwoord of een logregel)."""
        return (await self._dienst()).provider.provider_name

    async def complete_json(
        self, messages: Sequence[_Bericht], schema: object = None, **kwargs: object
    ) -> TenantAntwoord:
        """De vorm van `LLMService.complete_json`; het schema en `provider`/`model` van de aanroeper tellen niet."""
        return await self.chat_completion(messages, **kwargs)

    async def async_prompt(
        self, messages: Sequence[_Bericht], **kwargs: object
    ) -> TenantAntwoord:
        """De naam waaronder `ExecutionFeedbackAgent` en `WorkflowOrchestratorAgent` hem al aanroepen."""
        return await self.chat_completion(messages, **kwargs)

    @bewaakt_model_aanroep
    async def generate_response(self, prompt: str, **kwargs: object) -> TaalmodelAntwoord:
        """Het woordenboek dat `generate_response`-aanroepers (stapel A-stijl) lezen.

        Een `provider=`, `model=` of `response_format=` van de aanroeper wordt GENEGEERD: het model is de keuze
        van de tenant, niet van het verzoek (ADR-041 B14). Een lijst `messages=` vervangt de losse prompt.
        """
        try:
            dienst = await self._dienst()
            berichten = _als_berichten(kwargs.get("messages"))
            if berichten:
                inhoud = str(
                    await dienst.generate(
                        berichten,
                        temperature=_getal(kwargs.get("temperature")),
                        max_tokens=_geheel(kwargs.get("max_tokens")),
                    )
                )
            else:
                inhoud = await self.tekst(
                    prompt,
                    temperature=_getal(kwargs.get("temperature")),
                    max_tokens=_geheel(kwargs.get("max_tokens")),
                )
        except Exception as exc:
            logger.error(
                "taalmodel voor tenant %s mislukt (%s)",
                self.tenant_id,
                type(exc).__name__,
                exc_info=True,
            )
            # Alleen het TYPE naar de aanroeper (en zo naar de gebruiker): de tekst kan het adres of de
            # melding van het eindpunt van een klant bevatten. De volledige fout staat in het logboek.
            return {"success": False, "error": type(exc).__name__}
        return {
            "success": True,
            "content": inhoud,
            "text": inhoud,
            "model": dienst.provider.config.model,
            "provider": dienst.provider.provider_name,
        }

    @bewaakt_model_aanroep
    async def text_completion(self, prompt: str, **kwargs: object) -> TenantAntwoord:
        """De vorm van `LLMClient.text_completion`: een losse prompt als een gebruikersbericht."""
        return await self.chat_completion([LLMMessage(role="user", content=prompt)], **kwargs)

    @bewaakt_model_aanroep
    async def generate(
        self,
        messages: Sequence[_Bericht],
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **_rest: object,
    ) -> str:
        """De vorm van `LLMService.generate` (stapel B): de TEKST, een storing is een uitzondering."""
        berichten = [LLMMessage(role=m.role, content=m.content) for m in messages]
        if system_prompt:
            berichten.insert(0, LLMMessage(role="system", content=system_prompt))
        dienst = await self._dienst()
        return str(await dienst.generate(berichten, temperature=temperature, max_tokens=max_tokens))

    @bewaakt_model_aanroep
    async def generate_with_tools(
        self, messages: Sequence[Mapping[str, object]], tools: object = None, **kwargs: object
    ) -> TaalmodelAntwoord:
        """De vorm van `LLMService.generate_with_tools` (stapel A).

        Stapel A gaf `tools` ook niet door: de brug was `generate_response(prompt="", messages=...)` en de
        toolbeschrijving staat in de prompt zelf. `provider=`, `model=` en `model_id=` van de aanroeper
        tellen niet: het model is dat van de tenant.
        """
        return await self.generate_response(
            "", messages=list(messages), temperature=kwargs.get("temperature")
        )

    async def initialize(self) -> bool:
        """Haalt het model van de tenant op; een fout komt als uitzondering bij de aanroeper."""
        await self._dienst()
        return True

    async def get_service_status(self) -> dict[str, object]:
        """Welke verwerker dit is; zonder gezondheidsmeting (die hoort bij het platform, niet bij een tenant)."""
        return {
            "status": "tenant",
            "tenant_id": self.tenant_id,
            "provider": await self.provider_naam(),
        }

    @bewaakt_model_aanroep
    async def chat_completion(self, messages: Sequence[_Bericht], **kwargs: object) -> TenantAntwoord:
        """De vorm van `LLMClient.chat_completion`: `.content` en `.success`, nooit een verzonnen succes."""
        berichten = [LLMMessage(role=m.role, content=m.content) for m in messages]
        try:
            dienst = await self._dienst()
            inhoud = str(
                await dienst.generate(
                    berichten,
                    temperature=_getal(kwargs.get("temperature")),
                    max_tokens=_geheel(kwargs.get("max_tokens")),
                )
            )
        except Exception as exc:
            logger.error(
                "taalmodel voor tenant %s mislukt (%s)",
                self.tenant_id,
                type(exc).__name__,
                exc_info=True,
            )
            return TenantAntwoord(
                content="", success=False, error_message=type(exc).__name__
            )
        return TenantAntwoord(
            content=inhoud,
            model=dienst.provider.config.model,
            provider=dienst.provider.provider_name,
        )


def _als_berichten(waarde: object) -> list[LLMMessage]:
    """Berichten als woordenboeken of objecten met `.role` en `.content` naar `LLMMessage`."""
    if not isinstance(waarde, list):
        return []
    uit: list[LLMMessage] = []
    for bericht in waarde:
        if isinstance(bericht, dict):
            uit.append(
                LLMMessage(
                    role=str(bericht.get("role", "user")), content=str(bericht.get("content", ""))
                )
            )
        else:
            uit.append(
                LLMMessage(
                    role=str(getattr(bericht, "role", "user")),
                    content=str(getattr(bericht, "content", "")),
                )
            )
    return uit


def _platformstandaard() -> LLMService:
    """Mistral (EU) voor een verzoek zonder tenant; een ontbrekende sleutel is een duidelijke fout."""
    from src.core.services.llm.factory import ProviderFactory
    from src.core.services.llm.providers.mistral import gekozen_model

    try:
        provider = ProviderFactory.create("mistral", model=gekozen_model())
    except ValueError as exc:
        raise TenantLLMNietBeschikbaarError(str(exc)) from exc
    return LLMService(provider_instance=provider)


def _getal(waarde: object) -> float | None:
    if isinstance(waarde, (int, float)) and not isinstance(waarde, bool):
        return float(waarde)
    return None


def _geheel(waarde: object) -> int | None:
    if isinstance(waarde, (int, float)) and not isinstance(waarde, bool):
        return int(waarde)
    return None


async def keuze_van_de_tenant(tenant_id: int) -> str:
    """De taalmodelkeuze van de tenant (`mistral` of `ollama`), uit dezelfde bron als `for_tenant`.

    Een leesfout is een fout, geen standaardkeuze: kon de keuze niet gelezen worden, dan is niet te zeggen of
    de klant `ollama` koos (zie `LLMService._keuze_van_de_klant`).
    """
    from src.core.database.session import get_db_session
    from src.core.services.tenant_llm_provider_service import bouw_tenant_llm_service
    from src.core.shared.tenant_llm_keuze import keuze_uit_instellingen

    async with get_db_session() as db:
        instellingen = await bouw_tenant_llm_service(db).instellingen_van_de_klant(tenant_id)
    return keuze_uit_instellingen(instellingen)
