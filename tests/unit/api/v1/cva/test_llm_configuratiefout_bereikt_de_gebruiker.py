"""Een verkeerde providernaam moet als CONFIGURATIEFOUT bij de mens aankomen.

Gemeten bij Gate 2, ronde 3 (2026-09-20). `LLMProviderUnknownError` is bewust geen
`ValueError`, zodat `LLMService.__init__` hem niet opeet en stil de MockProvider teruggeeft.
Gevolg dat niemand had voorzien: op de twee plekken die deze fout voor een MENS vertalen werd
hij daardoor ook niet meer gevangen.

- `get_llm_service_dependency` gaf een kale HTTP 500 in plaats van de 503 met
  "Check LLM_PROVIDER and LLM_MODEL" die er expliciet voor is geschreven.
- `probe_llm_health` meldde `config_error: False`, waarmee de CVA-health de beheerder naar
  zijn SLEUTEL stuurde terwijl zijn providerNAAM fout stond.

De fout werd dus luider en tegelijk dommer. Deze tests leggen vast dat de melding aankomt op
de enige plek waar iemand hem leest.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.core.api.v1.cva import dependencies as dep
from src.core.services.llm.service import LLMService

ONBEKENDE_NAAM = "een-provider-die-niet-bestaat"


@pytest.fixture
def onbekende_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zet de omgeving op een providernaam die de fabriek niet kent."""
    monkeypatch.setenv("LLM_PROVIDER", ONBEKENDE_NAAM)
    monkeypatch.setenv("LLM_MODEL", "een-model")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)


@pytest.mark.asyncio
async def test_de_dependency_geeft_503_met_een_bruikbare_melding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Niet 500: dan staat er alleen "Internal Server Error" en zoekt de inrichter zich blind."""
    from src.core.shared.tenant_llm_keuze import TenantLLMNietBeschikbaarError

    async def zonder_sleutel(tenant_id: int) -> object:
        raise TenantLLMNietBeschikbaarError("MISTRAL_API_KEY ontbreekt")

    monkeypatch.setattr(LLMService, "for_tenant", staticmethod(zonder_sleutel))
    gebruiker = SimpleNamespace(tenant_id=7)

    with pytest.raises(HTTPException) as fout:
        await dep.get_llm_service_dependency(current_user=gebruiker)  # type: ignore[arg-type]

    assert fout.value.status_code == 503
    assert "MISTRAL_API_KEY" in str(fout.value.detail)


@pytest.mark.asyncio
async def test_de_health_probe_noemt_het_een_configuratiefout(
    onbekende_provider: None,
) -> None:
    """`config_error` stuurt de melding; op False wijst hij naar de verkeerde oorzaak."""
    uitslag = await dep.probe_llm_health()

    assert uitslag["available"] is False
    assert uitslag["config_error"] is True
    assert ONBEKENDE_NAAM in uitslag["message"]
