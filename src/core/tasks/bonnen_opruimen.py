"""De dagelijkse opruiming van geuploade bonnen (bonlezer dag 4).

Besluit Rakesh 2026-10-17: "30 dagen bewaren en zijn daarmee lezer". Deze taak verwijdert per tenant de
geuploade bonnen, hun metabestanden en het vastgelegde leesresultaat die ouder zijn dan 30 dagen
(`src/core/als/bonlezer/opruimen.py` doet het werk en weet precies welke bestanden wel en niet), en schrijft per
tenant EEN auditregel met alleen het AANTAL: geen bestandsnamen en geen inhoud.

Besluit Rakesh 2026-10-17 ("optie 2"): dezelfde taak verwijdert ook de BEVESTIGDE velden (`<bon>.bevestigd.json`)
nadat het einde van het kwartaal van de bondatum plus 3 maanden voorbij is; daarvoor volgt een eigen auditregel
(`bevestigde_bonnen_opgeruimd`, alleen het aantal).

- **Waar draait dit.** De scheduler zet de taak alleen in de wachtrij (`.send()`); de actor draait in de
  worker die het uploadvolume SCHRIJFBAAR heeft (`workflow-worker`, zie `docker-compose.yml`). De bonlezer-
  worker heeft dat volume bewust alleen-lezen.
- **De tenant komt uit de mapnaam**, die de backend zelf aanmaakte bij de upload; niet uit invoer van een
  gebruiker. De auditregel schrijft binnen die tenant (`adopt_tenant`).
- **Faalt de auditregel**, dan blijft de opruiming gedaan: het bestand is dan al weg en een tweede dagrun heeft
  niets meer te verwijderen (`best_effort`).
- **Geen herhaling** (`max_retries=0`): wat blijft liggen pakt de volgende dagrun.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from src.core.tasks.dramatiq_broker import workflow_actor
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.als.bonlezer.opruimen import BEWAARDAGEN, ruim_bevestigd_op, ruim_op, upload_map
from src.core.database.bypass_session import adopt_tenant
from src.core.database.session import get_db_session
from src.core.governance.audit import AuditService
from src.core.tasks.eigen_loop import SessieFabriek, draai_in_eigen_loop
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)


async def _log_audit(sessie: AsyncSession, tenant_id: int, aantal: int) -> None:
    async with adopt_tenant(sessie, tenant_id):
        async with best_effort("bonnen opruimen audit", db_session=sessie):
            await AuditService.log_action(
                tenant_id=tenant_id,
                action="bonnen_opgeruimd",
                resource="bonlezer_uploads",
                details={"bonnen_verwijderd": aantal, "bewaardagen": BEWAARDAGEN},
                session=sessie,
                endpoint="worker:ruim_bonnen_op",
            )
            await sessie.commit()


async def _log_audit_bevestigd(sessie: AsyncSession, tenant_id: int, aantal: int) -> None:
    async with adopt_tenant(sessie, tenant_id):
        async with best_effort("bevestigde bonnen opruimen audit", db_session=sessie):
            await AuditService.log_action(
                tenant_id=tenant_id,
                action="bevestigde_bonnen_opgeruimd",
                resource="bonlezer_uploads",
                details={"bevestigingen_verwijderd": aantal},
                session=sessie,
                endpoint="worker:ruim_bonnen_op",
            )
            await sessie.commit()


async def ruim_bonnen_op_async(
    sessie_fabriek: SessieFabriek | None = None,
    nu: datetime | None = None,
    root: Path | None = None,
) -> dict[int, int]:
    """Ruim bonnen en verlopen bevestigingen op, met per tenant een auditregel per soort.

    Geeft het aantal verwijderde BONNEN per tenant terug (de bevestigingen hebben een eigen auditregel).
    """
    # De bestandsbewerking in een thread: een grote map mag de event loop niet vasthouden.
    map_ = root or upload_map()
    uitkomst = await asyncio.to_thread(ruim_op, map_, nu=nu)
    bevestigd = await asyncio.to_thread(ruim_bevestigd_op, map_, nu=nu)
    if not uitkomst and not bevestigd:
        return uitkomst
    fabriek = sessie_fabriek or get_db_session
    async with fabriek() as sessie:
        for tenant_id, aantal in uitkomst.items():
            await _log_audit(sessie, tenant_id, aantal)
        for tenant_id, aantal in bevestigd.items():
            await _log_audit_bevestigd(sessie, tenant_id, aantal)
    return uitkomst


@workflow_actor(
    queue_name="default",
    max_retries=0,
    time_limit=600_000,
    actor_name="ruim_bonnen_op",
)
def ruim_bonnen_op() -> None:
    """Dramatiq-ingang: een keer per dag door de scheduler gestart."""

    async def _taak(fabriek: SessieFabriek) -> None:
        await ruim_bonnen_op_async(sessie_fabriek=fabriek)

    draai_in_eigen_loop(_taak)
