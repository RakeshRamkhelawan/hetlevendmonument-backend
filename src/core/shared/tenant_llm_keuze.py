"""De taalmodelkeuze van een klant: standaard Mistral (EU), Ollama (eigen model) als tweede.

Brief: docs/agent-briefs/generated/2026-10-15-sprint-dag-mistral-als-eu-taalmodel.md (ADR-041 B14,
besluit Rakesh 2026-10-15: een gehuurd model in de EU, per klant schakelbaar naar een eigen model,
nooit stil terugvallen).

De keuze staat in `tenants.settings["llm_provider"]` -- de bestaande JSON-kolom, dus geen migratie.
Dit bestand is de ENE plek die zegt welke waarden bestaan en welke providers bij een keuze horen;
de terugvalketen (`llm/fallback_chain`, stapel A) en `LLMService.for_tenant` (`services/llm`, stapel B)
vragen het hier; het staat in `shared` zodat geen van beide stapels van de andere afhangt.

**De regels.**
- Zonder instelling is de keuze `mistral`.
- Een onbekende of verboden waarde (`deepseek`, `mock`, ...) is een FOUT en valt NIET stil terug op de
  standaard: een klant die iets anders dacht te hebben ingesteld, hoort dat te horen.
- `mistral` mag bij een storing doorvallen op het EIGEN model (ollama, lmstudio): dat is geen
  gehuurd model en de gegevens blijven binnen de omgeving.
- `ollama` valt NOOIT door naar een gehuurd model; bij een storing volgt een duidelijke fout.
- DeepSeek (geen verwerkersovereenkomst, ADR-041 B14) en mock (een namaakmodel) staan op geen enkele lijst.

**Mistral en de vlag `tenants.externe_providers_toegestaan`.** Die vlag (standaard FALSE) is de
"lokaal-alleen"-schakelaar voor KLANT-EIGEN eindpunten (`tenant_llm_providers`, BE-LLM-003/004): staat hij uit,
dan weigert het schrijfpad een extern eindpunt dat de klant zelf opgeeft. Hij blokkeert Mistral NIET. Mistral
is de platformverwerker die het platform zelf kiest, met een verwerkersovereenkomst die Rakesh regelt; een
klant die Mistral niet wil, kiest `ollama`. Zouden we de vlag wel laten gelden, dan werkte Mistral voor
niemand (alle tenants staan standaard op FALSE). Bron: Besluit Rakesh 2026-10-15 ("1. c": gehuurd taalmodel in de EU, per klant schakelbaar naar een eigen model; leverancier Mistral AI; DPA, opt-out training en zero data retention regelt hij zelf), bevestigd door de regie (sessie sanskritisetu-org-90) op 2026-10-19.
Spec: docs/backend/features/BE-LLM-006-mistral-eu-standaardmodel.md.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
STANDAARD_KEUZE = "mistral"

#: Leveranciers die NOOIT klantgegevens krijgen via een platformpad (brief 2026-10-19, ADR-041 B14).
#: Een klant die zijn EIGEN eindpunt opgeeft, is een andere zaak: dat is zijn keuze en zijn contract.
LEVERANCIERS_ZONDER_VERWERKERSOVEREENKOMST: frozenset[str] = frozenset({"deepseek", "qwen"})


def namaak_toegestaan() -> bool:
    """Een namaakmodel is alleen in tests toegestaan (`TESTING` staat in `tests/conftest.py`).

    Nooit in productie, ook niet als `TESTING` daar per ongeluk gezet is (Gate 2, 2026-10-20).
    """
    if os.environ.get("ENVIRONMENT", "").strip().lower() == "production":
        return False
    return os.environ.get("TESTING", "").strip().lower() in {"1", "true", "yes"}

#: Welke providers bij welke keuze mogen worden aangeroepen, in de volgorde van voorkeur.
_TOEGESTAAN: dict[str, tuple[str, ...]] = {
    "mistral": ("mistral", "ollama", "lmstudio"),
    "ollama": ("ollama", "lmstudio"),
}
TOEGESTANE_KEUZES: tuple[str, ...] = tuple(_TOEGESTAAN)
INSTELLING = "llm_provider"


class TenantLLMKeuzeFout(ValueError):
    """De taalmodelkeuze van een klant kon niet worden toegepast.

    De agentdeur (`BaseSpecialistAgent._get_llm_service`) laat deze fout DOOR in plaats van terug te
    vallen op het platformmodel: dat is op staging en productie DeepSeek, en een klant die `ollama`
    koos mag niet stil bij een gehuurd model uitkomen (Gate 2, 2026-10-19).
    """


class OnbekendeLLMKeuzeError(TenantLLMKeuzeFout):
    """De tenantinstelling `llm_provider` bevat geen toegestane keuze."""


class TenantLLMNietBeschikbaarError(TenantLLMKeuzeFout):
    """De gekozen provider is niet te gebruiken (bijvoorbeeld een ontbrekende sleutel)."""


def keuze_uit_instellingen(instellingen: Mapping[str, object] | None) -> str:
    """De gekozen provider uit `tenants.settings`; `mistral` als er niets is ingesteld."""
    if not isinstance(instellingen, Mapping) or INSTELLING not in instellingen:
        return STANDAARD_KEUZE
    ruw = instellingen[INSTELLING]
    keuze = ruw.strip().lower() if isinstance(ruw, str) else ""
    if keuze not in _TOEGESTAAN:
        raise OnbekendeLLMKeuzeError(
            f"De taalmodelkeuze van deze omgeving ({str(ruw)[:40]!r}) bestaat niet. "
            f"Toegestaan: {', '.join(TOEGESTANE_KEUZES)}."
        )
    return keuze


def behoud_llm_keuze(oud: Mapping[str, object] | None, nieuw: dict[str, object]) -> dict[str, object]:
    """Een wijziging die de instellingen VERVANGT, laat de taalmodelkeuze niet stil verdwijnen.

    `update_tenant` zet `settings` als geheel. Zonder dit verloor een klant die `ollama` koos die
    keuze bij elke wijziging van een andere instelling, en stond hij daarna stil op het gehuurde
    standaardmodel (een privacyverlaging zonder melding). Een uitdrukkelijk nieuwe waarde wint.
    """
    if INSTELLING in nieuw or not isinstance(oud, Mapping) or INSTELLING not in oud:
        return nieuw
    return {**nieuw, INSTELLING: oud[INSTELLING]}


def provider_mag_voor_keuze(provider: str, keuze: str) -> bool:
    """Mag een verzoek van een tenant met deze keuze naar deze provider? Een onbekende keuze: nee."""
    return provider.strip().lower() in _TOEGESTAAN.get(keuze, ())
