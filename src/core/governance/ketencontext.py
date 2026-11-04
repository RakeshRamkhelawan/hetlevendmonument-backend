"""De ketenlookup draait onder de klantcontext van de regel zelf (Gate 2 F1, ADR-036 OP-246).

**Het probleem.** Sinds `20261024_audit_leesregel` ziet de applicatierol in `audit_logs` alleen de rijen van de klant uit
`app.current_tenant`. Alle schrijvers ketenen aan de laatste hash van de klant VOOR WIE ze schrijven. Schrijft een sessie met
de context van klant A een regel voor klant B (of zonder context), dan zag de lookup de keten van B niet: elke regel kreeg
`previous_hash = NULL`, de keten splitste stil en `verify_chain` meldde manipulatie, terwijl de schrijver `True` kreeg.

**De oplossing.** Alleen de LOOKUP draait onder de context van de klant van de regel; de context van de sessie wordt daarna
teruggezet. `set_config(..., true)` geldt tot het einde van de transactie, dus de terugzetting is geen luxe: de rest van het
verzoek draait onder de oorspronkelijke klant. Het slot hangt niet van de context af (een advisory lock kent geen RLS).
De INSERT zelf is open (`rls_audit_logs_schrijven`) en heeft geen context nodig.

Geen `SECURITY DEFINER`: het kan met de context.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_LEES = text("SELECT current_setting('app.current_tenant', true)")
_ZET = text("SELECT set_config('app.current_tenant', :klant, true)")


def _is_postgresql(db: AsyncSession) -> bool:
    """RLS bestaat alleen in PostgreSQL; op SQLite (unit-tests) en op een nepsessie is er niets om te zetten."""
    try:
        return bool(db.get_bind().dialect.name == "postgresql")
    except Exception:  # noqa: BLE001 - een nepsessie of een ontbrekende bind betekent: geen PostgreSQL
        return False


@asynccontextmanager
async def ketencontext(db: AsyncSession, tenant_id: int) -> AsyncIterator[None]:
    """Draai de ketenlookup onder de klantcontext van `tenant_id`; herstel daarna de oorspronkelijke."""
    if not _is_postgresql(db):
        yield
        return
    vorige = (await db.execute(_LEES)).scalar()
    await db.execute(_ZET, {"klant": str(int(tenant_id))})
    try:
        yield
    finally:
        try:
            await db.execute(_ZET, {"klant": vorige or ""})
        except Exception:  # noqa: BLE001 - na een mislukte statement is de transactie al afgebroken
            logger.debug(
                "ketencontext: klantcontext niet teruggezet (transactie afgebroken)", exc_info=True
            )
