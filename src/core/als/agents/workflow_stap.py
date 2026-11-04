"""Een agentstap in een workflow: de GEKOZEN agent draait, met alleen de rechten van de starter.

Agentstap dag 1 (brief 2026-10-24, Keten G van de meetlat). Tot nu toe kon een agentstap geen enkele agent
starten: de router zocht een levende agent via een methode die niet bestaat en negeerde bovendien de keuze van
de klant (gemeten 2026-10-23, zie `tests/architecture/test_agentstap_en_taalmodelstap_voeren_geen_tool_uit_zonder_startertoets.py`).
Deze module lost dat op met het bestaande mechanisme van de ALS-catalogus (`EnterpriseCatalogLoader.get_agent_instance`),
zonder een nieuwe fabriek en zonder router-keuze.

**Kiesbaar = uitvoerbaar.** Een agent is uitvoerbaar in een workflow als er een ECHTE skill voor bestaat
(`implemented_agent_keys`, zo'n 135 stuks) EN die skill een uitvoerpad heeft dat de mens die de workflow startte
meegeeft (`execute_with_manifest_prompt`, `UITVOERBARE_AGENT_SLEUTELS` in `packs.py`: vandaag vier). De overige skills
draaien via het OODA-pad zonder initiator; daar voert een skill bewust geen enkele tool uit (zie `specialist_base`),
dus aanbieden zou een stap geven die stilletjes niets doet. Een andere agent: de stap faalt bij het starten met een
Nederlandse reden.

**Alleen de rechten van de starter.** Elke tool die de agent in deze stap wil gebruiken gaat, VOOR de Council-poort,
door `starter_heeft_toolrecht` (hetzelfde als een toolstap) en daarna door de Council, de HITL-vloer en de broker met
het profiel van die agent. Een HITL-tool (`send_payment_reminder`) wordt een goedkeuringsticket (`/hitl`); de stap
meldt dat eerlijk als niet-uitgevoerd in plaats van te wachten.

**De klant komt van de uitvoering**, nooit uit de stapdefinitie of de invoer.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

logger = logging.getLogger(__name__)

#: Wat de klant te lezen krijgt als de gekozen agent (nog) niet in een workflow kan draaien.
REDEN_NIET_UITVOERBAAR = "deze agent kan nog niet in een workflow draaien"


class _Configuratie(Protocol):
    agent_id: str
    name: str
    class_name: str


class _Skill(Protocol):
    """Wat een uitvoerbare skill moet kunnen; `_toolrecht_toets` hoort bij `specialist_base`."""

    _toolrecht_toets: Callable[[str], Awaitable[bool]] | None

    async def execute_with_manifest_prompt(
        self, params: dict[str, object], *, initiated_by_user_id: int | None = None
    ) -> _Resultaat: ...


class _Resultaat(Protocol):
    success: bool
    result_data: object
    error_message: str | None


class _Stap(Protocol):
    agent_id: str


class _Pakket(Protocol):
    pack_id: str
    steps: list[_Stap]


class _Catalogus(Protocol):
    agents: dict[str, _Configuratie]
    packs: dict[str, _Pakket]

    def get_agent_instance(self, agent_key: str, tenant_id: int) -> _Skill: ...


#: Een agent die GEEN tool uitvoert maar zelf gegevens leest (`execute_with_manifest_prompt` roept `act()` niet aan),
#: komt nooit langs `starter_heeft_toolrecht`. Voor zo'n agent toetst de stap het leesrecht dat de API voor dezelfde
#: gegevens eist (`require_receipts_read`). Een agent die wel `act()` gebruikt hoort hier NIET: die wordt per tool
#: getoetst. Bewaakt door `tests/unit/als/test_agentstap_elke_uitvoerbare_agent_wordt_getoetst.py`.
EIGEN_LEESRECHT: dict[str, tuple[str, str]] = {
    "receiptscanner": ("receipts", "read"),
    "vatcompliance": ("receipts", "read"),
    # De crediteurenagent (crediteuren dag 2 en 3): zelfde recht als de API voor het uploaden van een factuur en het vragen van
    # een betaalvoorstel (`payables:write`). De goedkeuring van wat hij voorlegt blijft een eigen recht (`payables:approve`).
    "crediteuren": ("payables", "write"),
}

#: Agents die een EIGEN klantfunctie zijn en niet achter de pakketschakelaar vallen: de debiteurenagent (Keten B)
#: heeft een eigen recht (`receivables:*`); een klant zonder pakket `mkb.zero_admin` kan nog steeds herinneringen
#: voorstellen. Zelfde uitzondering als in `tests/architecture/test_pakketagent_heeft_een_bekende_aanroeper.py`.
EIGEN_KLANTFUNCTIE = frozenset({"dunning"})

#: Nederlandse naam en korte omschrijving per uitvoerbare agent, voor de lijst in de workflowbouwer (agentstap dag 2). Een
#: medewerker kiest op deze tekst, niet op een technische sleutel. Bewaakt door
#: `tests/unit/als/test_uitvoerbare_agents_hebben_een_nederlandse_naam.py`: elke uitvoerbare agent staat hier.
AGENT_BESCHRIJVING: dict[str, tuple[str, str]] = {
    "dunning": (
        "Debiteurenagent",
        "Volgt openstaande facturen op en zet een betalingsherinnering of aanmaning klaar ter goedkeuring.",
    ),
    "receiptscanner": (
        "Bonnen samenvatten",
        "Vat de bevestigde bonnen van een kwartaal samen: aantal en totalen.",
    ),
    "vatcompliance": (
        "Btw-overzicht",
        "Maakt een btw-overzicht (voorbetaalde btw per tarief) uit de bevestigde bonnen van een kwartaal.",
    ),
    "crediteuren": (
        "Crediteurenagent",
        "Verwerkt een gelezen inkoopfactuur en stelt betalingen voor; alles wat geld raakt legt hij voor aan een goedkeurder.",
    ),
    "skillsgaptraining": (
        "Vaardigheden en training",
        "Brengt vaardigheidstekorten van medewerkers in kaart en stelt een training voor; een mens beslist altijd.",
    ),
}

#: Wat de klant leest als er geen enkele agent te kiezen is (pakket staat uit).
GEEN_AGENTS_UITLEG = (
    "Er zijn voor uw bedrijf nog geen AI-agents beschikbaar. Vraag uw beheerder het pakket van de agent aan te zetten "
    "(onder Pakketten); daarna verschijnt de agent hier."
)

_catalogus_cache: _Catalogus | None = None


def _catalogus() -> _Catalogus:
    """De ALS-catalogus, een keer per proces geladen (elke stap las anders alle manifesten opnieuw)."""
    global _catalogus_cache
    if _catalogus_cache is None:
        loader = importlib.import_module("src.core.als.agents.loader")
        geladen: _Catalogus = loader.EnterpriseCatalogLoader().load_all()
        _catalogus_cache = geladen
        return geladen
    return _catalogus_cache


def zoek_sleutel(catalogus: _Catalogus, agent_id: str) -> str | None:
    """De catalogussleutel bij wat de klant koos: de sleutel zelf of het volledige agent-id."""
    gekozen = agent_id.strip()
    if gekozen.lower() in catalogus.agents:
        return str(gekozen.lower())
    for sleutel, configuratie in catalogus.agents.items():
        if configuratie.agent_id == gekozen:
            return str(sleutel)
    return None


async def _pakket_staat_aan(sleutel: str, tenant_id: int, catalogus: _Catalogus) -> bool:
    """Staat een pakket waar deze agent in zit voor deze klant aan? Dezelfde schakelaar als `PACK_NOT_ENABLED`.

    Een agent in een pakket draait pas voor een klant nadat een beheerder het pakket heeft aangezet; geen rij is uit
    (`tenant_pack_activations`). Een agent die in geen enkel pakket zit, mag niet (fail-closed). De klant komt uit de
    uitvoering; de sessie krijgt zijn tenantcontext met `adopt_tenant` (een worker heeft er geen).
    """
    pakketten = [
        p.pack_id
        for p in catalogus.packs.values()
        if any(stap.agent_id.lower() == sleutel for stap in p.steps)
    ]
    if not pakketten:
        return False
    adopt = importlib.import_module("src.core.database.bypass_session").adopt_tenant
    db_manager = importlib.import_module("src.core.database.database").db_manager
    repo_klasse = importlib.import_module(
        "src.core.repositories.tenant_pack_activations_repository"
    ).TenantPackActivationsRepository
    async with db_manager.get_session() as sessie:
        async with adopt(sessie, tenant_id):
            repo = repo_klasse(sessie)
            for pakket in pakketten:
                if await repo.is_enabled(tenant_id, pakket):
                    return True
    return False


def _heeft_skill(sleutel: str, catalogus: _Catalogus) -> bool:
    """Bestaat er voor deze ene sleutel een echte skill? Importeert alleen die module, niet alle 139."""
    configuratie = catalogus.agents.get(sleutel)
    if configuratie is None:
        return False
    loader = importlib.import_module("src.core.als.agents.loader")
    try:
        module = importlib.import_module(f"src.core.als.agents.skills.{sleutel}")
    except ImportError:
        return False
    klasse = loader.EnterpriseCatalogLoader._skill_class_name(configuratie.class_name)
    return getattr(module, klasse, None) is not None


def uitvoerbare_agent_sleutels(catalogus: _Catalogus | None = None) -> set[str]:
    """De agents die een workflowstap kan uitvoeren: bedraad EN met een echte skill.

    Een bedrade sleutel zonder skill valt af (de catalogus kan een vermelding verliezen), dus de lijst
    blijft eerlijk. `importlib`: dezelfde Ce-reden als elders in deze map.
    """
    packs = importlib.import_module("src.core.als.enterprise.packs")
    bron = catalogus if catalogus is not None else _catalogus()
    return {s for s in packs.UITVOERBARE_AGENT_SLEUTELS if _heeft_skill(s, bron)}


def uitvoerbare_agents(catalogus: _Catalogus | None = None) -> list[dict[str, str]]:
    """Wat de workflowbouwer de klant aanbiedt: precies de agents die een stap kan uitvoeren, met een Nederlandse tekst."""
    bron = catalogus if catalogus is not None else _catalogus()
    uit: list[dict[str, str]] = []
    for sleutel in sorted(uitvoerbare_agent_sleutels(bron)):
        naam, omschrijving = AGENT_BESCHRIJVING.get(sleutel, (bron.agents[sleutel].name, ""))
        uit.append(
            {"agent_id": sleutel, "name": naam, "naam": naam, "omschrijving": omschrijving}
        )
    return uit


def _reden_van(fout: dict[str, object]) -> str:
    """De reden voor de klant. Een ruwe uitzonderingstekst (`tool_exception`) blijft in het log, niet in de uitvoer."""
    if fout.get("kind") == "tool_exception":
        logger.warning("Agentstap: tool %s mislukte: %s", fout.get("tool"), fout.get("error"))
        return f"de tool '{fout.get('tool')}' is mislukt"
    return str(fout.get("error") or fout.get("kind") or "onbekende fout")


async def uitvoerbare_agents_voor_klant(tenant_id: int) -> list[dict[str, str]]:
    """De agents die een agentstap voor DEZE klant uitvoert: uitvoerbaar EN het pakket staat aan (kiesbaar = uitvoerbaar).

    Een agent waarvan het pakket uit staat is niet kiesbaar: de stap zou pas bij het draaien weigeren. Een storing in
    de pakketcontrole sluit die agent uit (fail-closed) en staat in het log.
    """
    catalogus = _catalogus()
    zichtbaar: list[dict[str, str]] = []
    for agent in uitvoerbare_agents(catalogus):
        sleutel = agent["agent_id"]
        try:
            aan = sleutel in EIGEN_KLANTFUNCTIE or await _pakket_staat_aan(
                sleutel, tenant_id, catalogus
            )
        except Exception:
            logger.error("Agentlijst: pakketcontrole voor %s mislukte", sleutel, exc_info=True)
            aan = False
        if aan:
            zichtbaar.append(agent)
    return zichtbaar


REDEN_STORING = "de agent kon de opdracht niet uitvoeren door een storing"
REDEN_TE_DRUK = (
    "de AI-dienst heeft te veel verzoeken gekregen; probeer het over enkele minuten opnieuw "
    "(het is later meestal weer beschikbaar)"
)


def reden_bij_storing(fout: BaseException) -> str:
    """De reden voor de klant bij een onverwachte fout in de agent; nooit de tekst van de fout zelf.

    Meldt het taalmodel "te veel verzoeken" (HTTP 429), dan helpt wachten en dat zegt de reden dan ook. De fout kan in een
    andere fout zijn verpakt, dus de keten van oorzaken wordt gevolgd.
    """
    gezien: set[int] = set()
    huidig: BaseException | None = fout
    while huidig is not None and id(huidig) not in gezien:
        gezien.add(id(huidig))
        antwoord = getattr(huidig, "response", None)
        if getattr(antwoord, "status_code", None) == 429 or type(huidig).__name__ == "LLMRateLimitError":
            return REDEN_TE_DRUK
        huidig = huidig.__cause__ or huidig.__context__
    return REDEN_STORING


def _afgewezen(agent_id: str, reden: str, *, tijdelijk: bool = False) -> dict[str, object]:
    """Een weigering of mislukking met een Nederlandse reden; `tijdelijk` zegt of een nieuwe poging zin heeft."""
    return {
        "success": False,
        "agent_id": agent_id,
        "error": reden,
        "output": {"error": reden},
        "tijdelijk": tijdelijk,
    }


async def _weigering_voor_de_start(
    sleutel: str, tenant_id: int, starter_id: int, catalogus: _Catalogus
) -> str | None:
    """De reden waarom deze agent voor deze klant en starter NIET mag starten, of `None`.

    Twee voorwaarden voor de eerste tool: het pakket staat voor de klant aan (tenzij een eigen klantfunctie), en een
    agent die zelf gegevens leest (zonder tool) heeft het leesrecht van de starter.
    """
    if sleutel not in EIGEN_KLANTFUNCTIE and not await _pakket_staat_aan(
        sleutel, tenant_id, catalogus
    ):
        return "de agent is niet gestart: het pakket van deze agent staat voor uw bedrijf niet aan"
    if sleutel in EIGEN_LEESRECHT:
        resource, actie = EIGEN_LEESRECHT[sleutel]
        rbac = importlib.import_module("src.core.auth.rbac").rbac_service
        if not await rbac.user_has_resource_right(starter_id, resource, actie, tenant_id=tenant_id):
            return (
                "de agent is niet gestart: de gebruiker die deze workflow startte heeft geen recht "
                f"op {resource} ({actie})"
            )
    return None


async def voer_agentstap_uit(
    agent_id: str,
    instruction: str,
    *,
    tenant_id: object,
    starter: str | None,
) -> dict[str, object]:
    """Draai de gekozen agent voor deze stap. Geeft altijd een antwoord; `success: False` met een reden bij weigering."""
    if not isinstance(tenant_id, int) or isinstance(tenant_id, bool):
        return _afgewezen(
            agent_id, "de agent kon niet starten: de klant van de uitvoering ontbreekt"
        )
    if starter is None or not (starter.isascii() and starter.isdigit()) or int(starter) <= 0:
        # Zonder bekende mens is er niemand wiens recht getoetst kan worden (AI Act art. 14).
        return _afgewezen(
            agent_id,
            "de agent kon niet starten: er is geen gebruiker bekend die deze workflow startte",
        )

    catalogus = _catalogus()
    sleutel = zoek_sleutel(catalogus, agent_id)
    if sleutel is None or sleutel not in uitvoerbare_agent_sleutels(catalogus):
        return _afgewezen(agent_id, f"{REDEN_NIET_UITVOERBAAR} ({agent_id})")

    try:
        weigering = await _weigering_voor_de_start(sleutel, tenant_id, int(starter), catalogus)
    except Exception:
        # Een databasefout hier is geen weigering van de regels maar een storing; de klant krijgt een nette reden
        # en geen ruwe tekst, het detail staat in het log. Niet fail-open: de agent start niet.
        logger.error("Agentstap: controle voor de start van %s mislukte", sleutel, exc_info=True)
        weigering = (
            "de agent kon niet starten: het pakket en de rechten konden niet worden gecontroleerd"
        )
    if weigering is not None:
        return _afgewezen(agent_id, weigering)

    workflow_identiteit = importlib.import_module("src.core.tool_broker.workflow_identiteit")
    starter_id = int(starter)

    async def toets(tool_name: str) -> bool:
        return bool(
            await workflow_identiteit.starter_heeft_toolrecht(starter, tool_name, tenant_id)
        )

    skill = catalogus.get_agent_instance(sleutel, tenant_id)
    skill._toolrecht_toets = toets
    try:
        resultaat = await skill.execute_with_manifest_prompt(
            {"task": instruction}, initiated_by_user_id=starter_id
        )
    except Exception as fout:
        # Een storing in de agent (taalmodel, budget, database) is geen weigering; de klant krijgt een vaste reden en
        # het detail staat in het log. De uitzondering niet doorgeven: de engine zet `str(e)` in de uitvoering.
        logger.error("Agentstap: agent %s faalde onverwacht", sleutel, exc_info=True)
        # Een storing die tijdelijk is (te druk, netwerk) mag de engine opnieuw proberen; al het andere niet.
        foutsoort = importlib.import_module("src.core.workflow.foutsoort")
        return _afgewezen(
            agent_id, reden_bij_storing(fout), tijdelijk=bool(foutsoort.is_tijdelijke_fout(fout))
        )
    finally:
        skill._toolrecht_toets = None

    data = resultaat.result_data if isinstance(resultaat.result_data, dict) else {}
    fouten = [f for f in data.get("errors") or [] if isinstance(f, dict)]
    if resultaat.success and not fouten:
        return {"success": True, "agent_id": sleutel, "output": data}

    redenen = "; ".join(_reden_van(f) for f in fouten)
    if not redenen and resultaat.error_message:
        logger.warning("Agentstap: %s meldde: %s", sleutel, resultaat.error_message)
    reden = redenen or "de agent kon de opdracht niet uitvoeren"
    return {
        "success": False,
        "agent_id": sleutel,
        "error": reden,
        "output": {**data, "error": reden},
    }
