"""Een weggegooid CVA-bericht van een stilgezette klant: teller, logregel, auditregel (besluit C).

Staat hier en niet in `cva_tasks` zodat de actor maar een import naar de noodstop heeft (DSM-budget).
De auditregel bevat alleen het kanaal, nooit de tekst of de afzender (persoonsgegevens).
"""

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.bypass_session import adopt_tenant
from src.core.governance.audit import AuditService
from src.core.noodstop.metrics import CVA_BERICHTEN_WEGGEGOOID
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

SessieFabriek = Callable[[], AbstractAsyncContextManager[AsyncSession]]


async def registreer_weggegooid(
    tenant_id: int, channel: str, sessie_fabriek: SessieFabriek
) -> None:
    """Een weggegooid bericht: teller, logregel en een auditregel (zonder tekst of afzender)."""
    CVA_BERICHTEN_WEGGEGOOID.labels(channel=channel).inc()
    logger.warning(
        "CVA-bericht niet beantwoord voor klant %s (noodstop), kanaal %s", tenant_id, channel
    )
    try:
        async with sessie_fabriek() as sessie:
            async with adopt_tenant(sessie, tenant_id):
                async with best_effort("noodstop cva weggegooid audit", db_session=sessie):
                    await AuditService.log_action(
                        tenant_id=tenant_id,
                        action="noodstop_cva_bericht_weggegooid",
                        resource=f"cva_kanaal:{channel}",
                        details={"channel": channel},
                        session=sessie,
                        endpoint="worker:process_cva_message",
                    )
                    await sessie.commit()
    except Exception:
        # De teller en de logregel staan al; een sessie die niet te openen is mag het
        # weggooien niet in een fout veranderen.
        logger.error("noodstop: auditregel van een weggegooid CVA-bericht mislukt", exc_info=True)
