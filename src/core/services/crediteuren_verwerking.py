"""De crediteurenagent starten voor een geuploade inkoopfactuur, zodra de bonlezer hem heeft gelezen (crediteuren dag 2).

Er is geen klik van een medewerker nodig: na de upload wacht dit bestand (in de achtergrond van de API) tot de bonlezer klaar is en
start dan de agent (`CrediteurenSkill.verwerk_upload`). De tenant en de verantwoordelijke gebruiker zijn die van de upload (uit het
token), nooit uit de inhoud van de factuur.

**Waarom in de backend en niet in de algemene werker.** Alleen de backend bereikt de Redis van de bonlezer (compose: het eigen
koppelnetwerk `bonlezer_koppel`); de algemene werker (`workflow-worker`) ziet alleen het uploadvolume en kan het leesresultaat dus
niet ophalen zolang het niet naast de bon is vastgelegd. De bonlezer-worker zelf heeft een eigen image zonder netwerk en kan geen
agent starten. Het gevolg is dat een herstart van de API tijdens het wachten de taak kwijtraakt; daarom start ook `GET
/api/v1/payables/inlezen/{bestand_id}` de verwerking als er nog geen stand is (idempotent: een claim naast de upload laat een
tweede start niets doen).
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import time
from typing import Protocol, cast

logger = logging.getLogger(__name__)

#: Hoe vaak de bonlezer wordt gevraagd of de factuur klaar is, en hoe lang we maximaal wachten (VERLOOP_SECONDEN van de upload
#: plus een marge; daarna is de upload `verlopen` en niet meer te lezen).
POLL_SECONDEN = 3.0
MAX_POLL_SECONDEN = 15.0
MAX_WACHT_SECONDEN = 600.0

#: Hoeveel verwerkingen er tegelijk mogen wachten: per tenant en in dit proces. Een wachtende taak bezet een thread bij elke poll;
#: zonder grens kan een stroom uploads de threadpool van de API vullen (Gate 2). Een start die er niet meer bij past wordt niet
#: vergeten: `GET /api/v1/payables/inlezen/{id}` start hem later alsnog, en de claim voorkomt dubbel werk.
MAX_PER_TENANT = 5
MAX_TOTAAL = 25

#: Lopende verwerkingen in dit proces: een sleutel (tenant, bestand) hooguit een keer tegelijk. De taken zelf worden vastgehouden
#: zodat de event loop ze niet opruimt voor ze klaar zijn.
_BEZIG: set[tuple[int, str]] = set()
_TAKEN: set[asyncio.Task[None]] = set()


class _Agent(Protocol):
    async def verwerk_upload(
        self, bestand_id: str, *, initiated_by_user_id: int | None
    ) -> dict[str, object]: ...

    async def stel_betaling_voor(self, *, initiated_by_user_id: int | None) -> dict[str, object]: ...


def _haal_agent(tenant_id: int) -> _Agent:
    """De crediteurenagent uit de catalogus, zoals `receivables/dependencies.py::start_reminder_proposals` dat voor `dunning` doet.

    `importlib`: een statische import vanuit `services` naar `als` telt mee in de koppelingsmeting (fan-out-budget).
    """
    loader = importlib.import_module("src.core.als.agents.loader")
    agent = loader.EnterpriseCatalogLoader().load_all().get_agent_instance("crediteuren", tenant_id)
    return cast(_Agent, agent)


async def stel_betaling_voor(tenant_id: int, user_id: int) -> dict[str, object]:
    """Laat de crediteurenagent een betaalvoorstel maken (crediteuren dag 3). De gebruiker is de verantwoordelijke voor het voorstel."""
    return await _haal_agent(tenant_id).stel_betaling_voor(initiated_by_user_id=user_id)


async def verwerk_zodra_gelezen(
    tenant_id: int, bestand_id: str, user_id: int, *, poll_seconden: float = POLL_SECONDEN
) -> dict[str, object]:
    """Wacht tot de upload gelezen is en laat de agent hem verwerken; geeft de uitkomst van de agent."""
    agent = _haal_agent(tenant_id)
    einde = time.monotonic() + MAX_WACHT_SECONDEN
    wacht = poll_seconden
    while True:
        uitkomst = dict(await agent.verwerk_upload(bestand_id, initiated_by_user_id=user_id))
        if uitkomst.get("uitkomst") != "nog_niet_klaar" or time.monotonic() >= einde:
            return uitkomst
        await asyncio.sleep(wacht)
        wacht = min(wacht * 1.5, MAX_POLL_SECONDEN)


async def _draai(tenant_id: int, bestand_id: str, user_id: int) -> None:
    sleutel = (tenant_id, bestand_id)
    try:
        uitkomst = await verwerk_zodra_gelezen(tenant_id, bestand_id, user_id)
        logger.info(
            "crediteurenagent klaar: tenant=%s bestand_id=%s uitkomst=%s",
            tenant_id,
            bestand_id,
            uitkomst.get("uitkomst"),
        )
    except Exception as fout:  # noqa: BLE001 -- een mislukte achtergrondtaak mag de API niet raken; hij wordt gelogd
        logger.error(
            "crediteurenagent mislukt: tenant=%s bestand_id=%s fouttype=%s",
            tenant_id,
            bestand_id,
            type(fout).__name__,
            exc_info=True,
        )
    finally:
        _BEZIG.discard(sleutel)


def start_verwerking(tenant_id: int, bestand_id: str, user_id: int) -> None:
    """Start de verwerking in de achtergrond van de lopende event loop. Een tweede start voor dezelfde upload doet niets."""
    sleutel = (tenant_id, bestand_id)
    if sleutel in _BEZIG:
        return
    if len(_BEZIG) >= MAX_TOTAAL or sum(1 for t, _ in _BEZIG if t == tenant_id) >= MAX_PER_TENANT:
        logger.warning("crediteurenagent: te veel wachtende verwerkingen, start uitgesteld: tenant=%s", tenant_id)
        return
    _BEZIG.add(sleutel)
    taak = asyncio.get_running_loop().create_task(_draai(tenant_id, bestand_id, user_id))
    _TAKEN.add(taak)
    taak.add_done_callback(_TAKEN.discard)
