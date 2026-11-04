"""`LLMService.for_tenant`: het taalmodel van DEZE klant, of eerlijk dat van het platform.

Dit is het sluitstuk van fase 2b. Fase 2a gaf een klant de mogelijkheid zijn eigen eindpunt en
sleutel te laten inrichten; `keten()` had daarna nul aanroepers, dus de opslag had geen
gebruiker. Deze tests leggen de vier eigenschappen vast die dat pad moet hebben.

De keten wordt hier INGESPOTEN via een dubbel voor `bouw_tenant_llm_service`. Dat is bewust:
een test die een echte database opzet, meet de repository en niet de resolutie, en zou bij elke
schemawijziging omvallen om een reden die niets met dit pad te maken heeft.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from src.core.services import tenant_llm_provider_service as tlps
from src.core.services.llm.service import LLMService

GEHEIM = "s" + "k-test"

def _rij(
    naam: str = "klant-a",
    base_url: str = "https://llm.klant.test/v1",
    ip: str | None = "203.0.113.7",
    volgorde: int = 1,
) -> tlps.ProviderRij:
    return tlps.ProviderRij(
        volgorde=volgorde,
        naam=naam,
        base_url=base_url,
        model="model-a",
        gevalideerd_ip=ip,
        api_key=GEHEIM,
    )


class _NepDienst:
    """Het dubbel kent de twee helften apart, net als de echte dienst sinds BE-LLM-005.

    `opgeslagen_rijen()` is het databasedeel en `beproef()` het netwerkdeel. Ze staan los
    omdat `for_tenant` de sessie sluit tussen die twee -- een dubbel met alleen `keten()`
    zou dat verschil verbergen en de test zou groen blijven als de sessie weer openbleef.
    """

    def __init__(self, keten: list[tlps.ProviderRij]) -> None:
        self._keten = keten
        self.volgorde_van_aanroepen: list[str] = []
        self.sessie: _NepSessie | None = None
        self.sessie_open_tijdens_adrescontrole: bool | None = None
        self.gekregen_rijen: list[tlps.ProviderRij] | None = None

    async def opgeslagen_rijen(self, tenant_id: int) -> list[tlps.ProviderRij]:
        self.volgorde_van_aanroepen.append("database")
        return list(self._keten)

    async def beproef(
        self, tenant_id: int, rijen: list[tlps.ProviderRij]
    ) -> list[tlps.ProviderRij]:
        self.volgorde_van_aanroepen.append("adrescontrole")
        if self.sessie is not None:
            self.sessie_open_tijdens_adrescontrole = self.sessie.open
        # De ONTVANGEN lijst vasthouden. Zonder dit negeerde het dubbel zijn argument, en dan
        # bleef de koppeling "de rijen uit de database zijn de rijen die de adrescontrole in
        # gaan" ongeassert -- een mutatie die `beproef(tenant_id, [])` aanroept was groen.
        self.gekregen_rijen = list(rijen)
        return self._keten

    async def instellingen_van_de_klant(self, tenant_id: int) -> None:
        return None

    async def keten(self, tenant_id: int) -> list[tlps.ProviderRij]:
        return await self.beproef(tenant_id, await self.opgeslagen_rijen(tenant_id))


class _NepSessie:
    """Een sessie die opengaat en dicht, en dat bijhoudt."""

    def __init__(self) -> None:
        self.open = False

    async def __aenter__(self) -> _NepSessie:
        self.open = True
        return self

    async def __aexit__(self, *_uitzondering: object) -> None:
        self.open = False


#: Wat de fixture teruggeeft: zet de keten klaar en lever het dubbel op.
_ZetKeten = Callable[[list[tlps.ProviderRij]], "_NepDienst"]


@pytest.fixture
def met_keten(monkeypatch: pytest.MonkeyPatch) -> _ZetKeten:
    """Zet de keten klaar EN vervang de databasesessie.

    `for_tenant` opent sinds BE-LLM-005 zijn eigen sessie (kort, en dicht voordat de
    adrescontrole begint). In een unittest mag daar geen echte database aan te pas komen.
    """
    import src.core.database.session as sessie_module

    def _zet(rijen: list[tlps.ProviderRij]) -> _NepDienst:
        dubbel = _NepDienst(rijen)
        sessie = _NepSessie()
        dubbel.sessie = sessie
        monkeypatch.setattr(tlps, "bouw_tenant_llm_service", lambda db: dubbel)
        monkeypatch.setattr(sessie_module, "get_db_session", lambda: sessie)
        return dubbel

    return _zet


@pytest.mark.asyncio
async def test_de_klant_krijgt_zijn_EIGEN_eindpunt(met_keten: _ZetKeten) -> None:
    met_keten([_rij()])

    dienst = await LLMService.for_tenant(1)

    assert dienst.provider.config.base_url == "https://llm.klant.test/v1"
    assert dienst.provider.config.api_key == GEHEIM
    assert dienst.provider.config.pinned_ip == "203.0.113.7"
    assert dienst.provider.config.sni_hostname == "llm.klant.test"


@pytest.mark.asyncio
async def test_een_lege_keten_levert_de_keuze_van_de_klant(
    met_keten: _ZetKeten, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Geen rijen, noodknop uit, of elke rij overgeslagen: dan gewoon doorwerken.

    De tegenrichting van dit hele pad. Zonder deze test is "weiger alles" een geldige
    implementatie, en een klant zonder eigen provider hoort niet zonder taalmodel te zitten.
    Sinds de Mistral-brief (2026-10-19) is dat zijn keuze (standaard Mistral), niet meer de
    platformstandaard uit `LLM_PROVIDER`; zie `test_tenant_llm_keuze.py`.
    """
    met_keten([])
    monkeypatch.setenv("MISTRAL_API_KEY", "test-" + "nepsleutel-0123456789")

    dienst = await LLMService.for_tenant(1)

    assert dienst.provider.config.base_url != "https://llm.klant.test/v1"
    assert dienst.provider.config.pinned_ip is None


@pytest.mark.asyncio
async def test_een_rij_die_mock_heet_levert_GEEN_namaakmodel(met_keten: _ZetKeten) -> None:
    """De naam van een klantrij is een vrij tekstveld en mag geen klasse kiezen.

    Gemeten faalvorm: via `ProviderFactory.create()` zou deze rij de MockProvider opleveren --
    in productie een harde fout op onze eigen guard, daarbuiten plausibele verzonnen tekst.
    """
    met_keten([_rij(naam="mock")])

    dienst = await LLMService.for_tenant(1)

    assert dienst.provider.serves_mock is False
    assert dienst.provider.provider_name == "mock"  # het ETIKET blijft wat de klant koos
    assert dienst.provider.config.base_url == "https://llm.klant.test/v1"


@pytest.mark.asyncio
async def test_bij_een_adres_met_een_IP_gaat_er_geen_servernaam_mee(met_keten: _ZetKeten) -> None:
    """Een IP is geen geldige SNI-waarde; die meesturen breekt de handdruk.

    Dit is geen randgeval: de lokale bodem van de keten is een IP-adres.
    """
    met_keten([_rij(base_url="https://203.0.113.7/v1", ip="203.0.113.7")])

    dienst = await LLMService.for_tenant(1)

    assert dienst.provider.config.sni_hostname is None


@pytest.mark.asyncio
async def test_de_sessie_is_DICHT_voordat_de_adrescontrole_begint(met_keten: _ZetKeten) -> None:
    """De uitgestelde bevinding uit BE-LLM-004, nu vastgelegd (BE-LLM-005).

    De adrescontrole doet per rij een naamsopzoeking van maximaal vijf seconden. Zolang die
    binnen de sessie van de aanroeper stond, hield elke agenttaak een databaseverbinding bezet
    voor de duur van al die opzoekingen -- met een keten van vier rijen twintig seconden, op
    een database die op 40 van de 50 verbindingen zit. `.claude/rules/database.md` verbiedt
    het: geen transactie open tijdens externe I/O.

    Wat deze test NIET toestaat is de goedkope oplossing: de controle verplaatsen naar NA het
    gebruik. De volgorde blijft eerst database, dan adrescontrole -- en de controle blijft dus
    voor het eerste verzoek. Dat is de hele reden dat hij bestaat (DNS-rebinding).
    """
    dubbel = met_keten([_rij()])

    await LLMService.for_tenant(1)

    assert dubbel.volgorde_van_aanroepen == ["database", "adrescontrole"]
    assert dubbel.sessie_open_tijdens_adrescontrole is False, (
        "de databasesessie stond nog open tijdens de adrescontrole; dan houdt elke agenttaak "
        "een verbinding bezet voor de duur van de naamsopzoekingen"
    )


@pytest.mark.asyncio
async def test_de_breakersleutel_draagt_de_TENANT(met_keten: _ZetKeten) -> None:
    """Zonder de tenant in de sleutel delen twee klanten een circuit breaker.

    De gedragstest in `test_de_keten_valt_door_naar_de_volgende_rij.py` bouwt zijn sleutels
    ZELF en kan dus niet zien wat `for_tenant` ervan maakt. Deze test kijkt naar de sleutels
    die daadwerkelijk worden gebouwd -- precies het gat waar de faalvorm in past: de twin
    sleutelt op klassenaam plus index, en met die vorm zet het uitvallen van klant A de
    provider van klant B op open.
    """
    met_keten([_rij(), _rij(naam="klant-b", base_url="https://llm-b.klant.test/v1")])

    dienst = await LLMService.for_tenant(7)

    from src.core.services.llm.providers.failover import FailoverProvider

    assert isinstance(dienst.provider, FailoverProvider)
    ids = [schakel.breaker_id for schakel in dienst.provider._schakels]
    assert len(ids) == 2
    for breaker_id in ids:
        assert breaker_id.startswith("tenant:7|"), (
            f"de breaker-id '{breaker_id}' draagt de tenant niet; twee klanten delen dan een "
            "breaker en het uitvallen van de een sluit de provider van de ander af"
        )
    assert len(set(ids)) == 2, "twee rijen kregen dezelfde sleutel en dus dezelfde breaker"


@pytest.mark.asyncio
async def test_twee_rijen_op_DEZELFDE_host_krijgen_toch_hun_eigen_breaker(
    met_keten: _ZetKeten,
) -> None:
    """De `volgorde` in de sleutel is dragend, en was ongetest (Gate 2).

    Twee deployments of modellen op EEN eindpunt is een normale inrichting (Azure, vLLM). Zonder
    `volgorde` in de sleutel delen die twee rijen een breaker, en dan zet het uitvallen van rij 1
    meteen rij 2 op open -- failover volledig uit, binnen een klant. De bestaande tenant-test
    zag dat niet: die gebruikte twee verschillende hosts, dus de sleutels verschilden toch al.
    """
    met_keten([_rij(volgorde=1), _rij(volgorde=2)])

    dienst = await LLMService.for_tenant(7)

    from src.core.services.llm.providers.failover import FailoverProvider

    assert isinstance(dienst.provider, FailoverProvider)
    ids = [schakel.breaker_id for schakel in dienst.provider._schakels]
    assert len(set(ids)) == 2, (
        f"twee rijen op dezelfde host kregen dezelfde breaker-id ({ids}) en dus dezelfde "
        "breaker; dan schakelt het uitvallen van de een de ander uit"
    )


@pytest.mark.asyncio
async def test_de_rijen_uit_de_database_zijn_de_rijen_die_gecontroleerd_worden(
    met_keten: _ZetKeten,
) -> None:
    """De koppeling tussen de twee helften, die na het splitsen nergens meer vastlag."""
    rijen = [_rij(volgorde=1), _rij(volgorde=2)]
    dubbel = met_keten(rijen)

    await LLMService.for_tenant(1)

    assert dubbel.gekregen_rijen == rijen, (
        "de adrescontrole kreeg andere rijen dan de database opleverde; na het splitsen van "
        "`keten()` in twee helften is dat de enige plek waar die koppeling nog kan breken"
    )
