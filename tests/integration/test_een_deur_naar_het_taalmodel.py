"""De ene deur naar het taalmodel, met een ECHTE tenantrij in de testdatabase (brief 2026-10-19, ADR-041 B14).

De unittests (`tests/unit/llm/test_klantverzoeken_per_pad.py`) vervangen `LLMService.for_tenant`. Hier niet:
de keuze van de klant staat in `tenants.settings["llm_provider"]` en wordt door `for_tenant` zelf uit de
database gelezen. Het verkeer wordt op de HTTP-laag opgevangen (`tests/fixtures/taalmodel_verkeer.py`), met
`DEEPSEEK_API_KEY`, `GOOGLE_API_KEY` en `LLM_PROVIDER=deepseek` in de omgeving: de uitrol van vandaag.

Wat hier bewezen wordt, tegen echte data:
1. een tenant op de standaardkeuze (geen instelling) praat alleen met Mistral;
2. een tenant op `ollama` met een lokaal model dat uit staat krijgt een FOUT, en er gaat NIETS naar
   DeepSeek, Google of Mistral;
3. de keuze van tenant A beinvloedt tenant B niet.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.models.rbac_models import Tenant
from tests.fixtures.taalmodel_verkeer import installeer_verkeer

NEPSLEUTEL = "test-" + "mistral-" + "nepsleutel-0123456789"
ANDERE_SLEUTEL = "test-" + "andere-" + "nepsleutel-0123456789"
TENANT_STANDAARD = 9101
TENANT_OLLAMA = 9102

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _de_uitrol_van_vandaag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", ANDERE_SLEUTEL)
    monkeypatch.setenv("GOOGLE_API_KEY", ANDERE_SLEUTEL)
    monkeypatch.setenv("MISTRAL_API_KEY", NEPSLEUTEL)
    # `for_tenant` bouwt de klantketen en eist daarvoor een hoofdsleutel; een eigen sleutel per test.
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest_asyncio.fixture
async def tenants_met_keuze(postgres_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Twee echte, gecommitte tenantrijen; na afloop weer weg (dit zijn alleen onze eigen test-tenants)."""
    maker = async_sessionmaker(postgres_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as sessie:
        sessie.add(Tenant(id=TENANT_STANDAARD, name="Deur standaard", slug="deur-standaard-9101"))
        sessie.add(
            Tenant(
                id=TENANT_OLLAMA,
                name="Deur ollama",
                slug="deur-ollama-9102",
                settings={"llm_provider": "ollama"},
            )
        )
        await sessie.commit()
    try:
        yield
    finally:
        async with maker() as sessie:
            await sessie.execute(
                delete(Tenant).where(Tenant.id.in_([TENANT_STANDAARD, TENANT_OLLAMA]))
            )
            await sessie.commit()


@pytest.mark.asyncio
async def test_een_tenant_op_de_standaardkeuze_praat_alleen_met_mistral(
    monkeypatch: pytest.MonkeyPatch, tenants_met_keuze: None
) -> None:
    from src.core.services.llm.tenant_deur import TenantTaalmodel

    verkeer = installeer_verkeer(monkeypatch, "antwoord")

    antwoord = await TenantTaalmodel(TENANT_STANDAARD).generate_response("hallo")

    assert (antwoord["success"], verkeer.verboden(), sorted(set(verkeer.hosts))) == (
        True,
        [],
        ["api.mistral.ai"],
    )


@pytest.mark.asyncio
async def test_een_tenant_op_ollama_met_een_lokale_storing_krijgt_een_fout_en_geen_ander_model(
    monkeypatch: pytest.MonkeyPatch, tenants_met_keuze: None
) -> None:
    from src.core.services.llm.tenant_deur import TenantTaalmodel

    verkeer = installeer_verkeer(monkeypatch, "antwoord", onbereikbaar=("localhost", "127.0.0.1"))

    antwoord = await TenantTaalmodel(TENANT_OLLAMA).generate_response("hallo")

    # `lokaal_geprobeerd` is het bewijs dat de fout van het LOKALE model kwam en niet van iets anders
    # (een eerdere versie van deze test slaagde voor de verkeerde reden: de hoofdsleutel ontbrak).
    lokaal_geprobeerd = any(host in ("localhost", "127.0.0.1") for host in verkeer.hosts)
    assert (
        antwoord["success"],
        verkeer.verboden(),
        "api.mistral.ai" in verkeer.hosts,
        lokaal_geprobeerd,
    ) == (False, [], False, True)


@pytest.mark.asyncio
async def test_de_keuze_van_de_ene_tenant_verandert_het_model_van_de_andere_niet(
    monkeypatch: pytest.MonkeyPatch, tenants_met_keuze: None
) -> None:
    from src.core.services.llm.tenant_deur import TenantTaalmodel

    verkeer = installeer_verkeer(monkeypatch, "antwoord", onbereikbaar=("localhost", "127.0.0.1"))

    await TenantTaalmodel(TENANT_OLLAMA).generate_response("hallo")
    standaard = await TenantTaalmodel(TENANT_STANDAARD).generate_response("hallo")

    assert (standaard["success"], standaard["provider"], verkeer.verboden()) == (
        True,
        "mistral",
        [],
    )
