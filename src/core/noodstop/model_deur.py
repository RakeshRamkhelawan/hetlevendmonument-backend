"""Adapter van de modeldeur: de echte noodstopcontrole achter de poort `src.core.shared.model_deur`.

De poort (stdlib-only) draagt de decorators en haken. Deze module levert wat zij nodig heeft en meldt
zich bij het laden aan: de controle (`eis_model_actief`, fail-closed via de guard) en de
tenantcontext. Zie de moduledocstring van de poort voor het principe.
"""

from __future__ import annotations

import logging

from src.core.noodstop.guard import KlantStilgezet, eis_chat_actief
from src.core.noodstop.metrics import NOODSTOP_GEWEIGERD
from src.core.shared.model_deur import registreer

logger = logging.getLogger(__name__)


def _klant_uit_context() -> int | None:
    from src.core.middleware.tenant_context import get_tenant_id

    return get_tenant_id()


async def eis_model_actief(tenant_id: object) -> None:
    """Gooit `KlantStilgezet` tenzij zeker is dat de klant NIET stilstaat (fail-closed).

    De weigering is geteld (`deur="model"`) en gelogd, met de vaste Nederlandse chatmelding.
    """
    try:
        await eis_chat_actief(tenant_id)
    except KlantStilgezet as stop:
        NOODSTOP_GEWEIGERD.labels(deur="model").inc()
        logger.warning(
            "noodstop: modelaanroep geweigerd (klant %s, onbekend=%s); er is niets naar het model gegaan",
            tenant_id,
            stop.onbekend,
        )
        raise


registreer(eis_model_actief, _klant_uit_context)
