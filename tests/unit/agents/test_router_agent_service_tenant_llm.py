"""Dit pad gebruikt de PLATFORMsleutel, en belooft niets per tenant.

**Wat hier stond tot 2026-09-23, en waarom het weg moest.** Twee tests legden vast dat
`execute_request` de `tenant_id` DOORGAF aan `LLMProviderFactory.get_provider(...)`
(BE-WFL-006, "per-tenant LLM credentials"). Ze slaagden, en ze bewaakten niets: de fabriek
keek met die tenant in `_tenant_configs`, een woordenboek dat in heel `src/` en `tests/` door
NIETS werd gevuld -- gemeten 2026-09-22. Elke aanroep viel dus terug op de omgevingsvariabelen
van het platform, met of zonder tenant. De melding bij een ontbrekende sleutel luidde
bovendien "No Gemini API Key found for tenant" en suggereerde een inrichting per klant die
niet bestond.

Een test die een DOORGIFTE vastlegt naar een parameter die niets doet, houdt een belofte in
stand in plaats van een gedrag. Daarom zijn ze vervangen en niet geschrapt: de nieuwe tests
leggen vast wat dit pad WEL doet, zodat de dag dat iemand hier alsnog een tenant in wil, de
verandering zichtbaar is.

Wie een provider per tenant nodig heeft: `LLMService.for_tenant()` (BE-LLM-004), die de echte
keten uit `tenant_llm_providers` leest.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.router_agent_service import RouterAgentService, RoutingDecision, TaskCategory


def _gemini_decision() -> RoutingDecision:
    return RoutingDecision(
        category=TaskCategory.COMPLEX_REASONING,
        priority=8,
        suggested_model="gemini-pro",
        reasoning="Complex task requires cloud model",
    )


def _dienst_met_provider() -> tuple[RouterAgentService, MagicMock]:
    svc = RouterAgentService(client=MagicMock())
    provider = MagicMock()
    provider.api_key = True
    provider.text_completion = AsyncMock(
        return_value=MagicMock(success=True, content="Gemini response")
    )
    return svc, provider


@pytest.mark.asyncio
async def test_de_fabriek_krijgt_GEEN_tenant_mee() -> None:
    """De aanroep noemt alleen het providertype; een tenant hoort hier niet meer bij."""
    svc, provider = _dienst_met_provider()

    with (
        patch.object(svc, "route_request", new=AsyncMock(return_value=_gemini_decision())),
        patch("src.core.agents.router_agent_service.LLMProviderFactory") as fabriek,
    ):
        fabriek.get_provider.return_value = provider
        result = await svc.execute_request("explain quantum computing", tenant_id="tenant_99")

    fabriek.get_provider.assert_called_once_with(provider_type="gemini")
    assert "tenant_id" not in fabriek.get_provider.call_args.kwargs, (
        "dit pad mag geen tenant aan de oude fabriek meegeven: die negeert hem, en dan lijkt "
        "het alsof er een inrichting per klant bestaat"
    )
    assert result["executed_by"] == "gemini_provider"


@pytest.mark.asyncio
async def test_de_tenant_blijft_wel_in_het_ANTWOORD_staan() -> None:
    """De tenant hoort bij de administratie van het verzoek, niet bij de sleutelkeuze.

    Deze twee dingen werden door elkaar gehaald. Het antwoord mag best zeggen VOOR WIE er is
    gewerkt -- dat is een boekhoudkundig feit. Wat niet mag is dat diezelfde waarde de indruk
    wekt dat er met de sleutel van die klant is gewerkt.
    """
    svc, provider = _dienst_met_provider()

    with (
        patch.object(svc, "route_request", new=AsyncMock(return_value=_gemini_decision())),
        patch("src.core.agents.router_agent_service.LLMProviderFactory") as fabriek,
    ):
        fabriek.get_provider.return_value = provider
        result = await svc.execute_request("explain quantum computing", tenant_id="tenant_99")

    assert result["tenant_id"] == "tenant_99"


@pytest.mark.asyncio
async def test_zonder_sleutel_zegt_de_melding_PLATFORM_en_niet_tenant(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """De foutmelding wees naar de verkeerde plek om te zoeken.

    Zonder sleutel valt dit pad terug op Ollama; de reden staat in het log. Stond daar "for
    tenant", dan gaat de volgende beheerder de inrichting van die klant nalopen terwijl de
    platformsleutel ontbreekt.
    """
    svc, provider = _dienst_met_provider()
    provider.api_key = None

    with (
        caplog.at_level("WARNING"),
        patch.object(svc, "route_request", new=AsyncMock(return_value=_gemini_decision())),
        patch("src.core.agents.router_agent_service.LLMProviderFactory") as fabriek,
        patch.object(svc, "_call_ollama", new=AsyncMock(return_value="lokaal antwoord")),
    ):
        fabriek.get_provider.return_value = provider
        result = await svc.execute_request("explain quantum computing", tenant_id="tenant_99")

    assert result["executed_by"] == "ollama_fallback"

    # De TEKST is de enige productiewijziging op dit pad, en de naam van deze test belooft hem.
    # Zonder deze twee asserties was de wijziging terug te draaien zonder dat iets rood werd --
    # aangewezen door een Gate 2-reviewer.
    meldingen = " ".join(r.getMessage() for r in caplog.records)
    assert "platform" in meldingen.lower(), (
        "de melding zegt niet dat de PLATFORMsleutel ontbreekt; dan gaat een beheerder de "
        "inrichting van de klant nalopen terwijl daar niets te vinden is"
    )
    assert "for tenant" not in meldingen.lower()
