"""Dagelijkse planner: plant de purge in voor gebruikers van wie de AVG-termijn is verstreken.

Een wissingsaanvraag (`POST /api/gdpr/delete-all` of `.../users/{id}/erase`) zet
`users.deletion_scheduled_for = nu + 30 dagen` en wist niets. Deze job zoekt elke dag de
gebruikers op van wie die datum voorbij is en stuurt per gebruiker een purge naar de queue.

Waarom een planner en geen Dramatiq-vertraging van 30 dagen: de toestand staat in de database en
overleeft dus elke herstart of leegmaken van Redis. De planner is idempotent: een gebruiker die al
gepurged is heeft `deletion_scheduled_for = NULL` (de purge zet dat), en de purge zelf controleert
op het moment van uitvoeren opnieuw of de termijn echt om is en de aanvraag niet is ingetrokken
(`alleen_indien_vervallen=True`). Twee keer draaien, of draaien terwijl iemand intrekt, is dus veilig.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text

from src.core.actors.gdpr_purge import purge_user_data
from src.core.database.database import db_manager
from src.core.database.tenant_query_filter import TenantFilterBypass

logger = logging.getLogger(__name__)

# Bovengrens per run: de rest volgt morgen (de planner is idempotent), zodat een dag met veel
# verlopen termijnen de queue niet in een keer vult.
MAX_PER_RUN = 500


async def run_avg_purge_vervallen(nu: datetime | None = None) -> dict[str, int]:
    """Plan de purge in voor elke gebruiker wiens termijn is verstreken. Geeft {"ingepland": n}."""
    moment = nu or datetime.now(timezone.utc)
    async with db_manager.get_session() as db:
        with TenantFilterBypass():
            rijen = (
                await db.execute(
                    text(
                        "SELECT id, tenant_id FROM users "
                        "WHERE deletion_scheduled_for IS NOT NULL AND deletion_scheduled_for <= :nu "
                        "ORDER BY deletion_scheduled_for, id LIMIT :limiet"
                    ),
                    {"nu": moment, "limiet": MAX_PER_RUN},
                )
            ).all()

    ingepland = 0
    for user_id, tenant_id in rijen:
        try:
            purge_user_data.send(
                user_id=int(user_id),
                tenant_id=int(tenant_id),
                scope="all",
                alleen_indien_vervallen=True,
            )
            ingepland += 1
        except Exception as exc:
            # Een mislukte inplanning stopt de rest niet; morgen probeert de planner het opnieuw.
            logger.warning(
                "avg_purge_inplannen_mislukt: user_id=%s, tenant_id=%s: %s: %s",
                user_id,
                tenant_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
    logger.info("avg purge planner: %s purges ingepland", ingepland)
    return {"ingepland": ingepland}
