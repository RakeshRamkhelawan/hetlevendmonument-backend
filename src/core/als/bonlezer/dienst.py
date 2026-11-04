"""De echte `BonDienst`: uploadmap, opdracht naar de bonlezer-worker en het resultaat uit zijn Redis.

Een plek voor wat `bonnen/dependencies.py` eerst zelf deed, zodat ook de crediteurenagent (`tool_broker/payables_registry.py`) dezelfde
dienst gebruikt en geen tweede leespijplijn bouwt. Alleen een proces met `BONLEZER_BROKER_URL` kan het leesresultaat ophalen; dat
is de backend, niet de algemene werker (die zit niet op het koppelnetwerk van de bonlezer).
"""

from __future__ import annotations

import dramatiq

from src.core.als.bonlezer.upload import BonDienst
from src.core.als.bonlezer.worker import QUEUE, haal_resultaat, lees_bon, upload_root


def _verstuur(tenant_id: int, bestand_id: str) -> str:
    """Zet de opdracht op de wachtrij van de bonlezer; de tenant komt uit de aanroeper, niet uit het bestand."""
    return str(lees_bon.send(tenant_id, bestand_id).message_id)


def _haal(message_id: str) -> dict[str, object]:
    """De uitkomst uit de resultaatopslag van de bonlezer, zonder te wachten (`ResultMissing` als er nog niets is)."""
    bericht: dramatiq.Message[dict[str, object]] = dramatiq.Message(
        queue_name=QUEUE,
        actor_name=lees_bon.actor_name,
        args=(),
        kwargs={},
        options={},
        message_id=message_id,
    )
    return haal_resultaat(bericht)


def maak_dienst() -> BonDienst:
    return BonDienst(upload_root(), verstuur=_verstuur, haal=_haal)
