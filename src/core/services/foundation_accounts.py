"""Ongebruikte vertelleraccounts opruimen (BE-EP-056).

Wie op *Deel je verhaal* een inloglink aanvraagt, krijgt meteen een bezoekersaccount
(rol ``visitor``). Gebruikt iemand de link nooit, dan blijft er een account staan
met alleen een e-mailadres. Dat bewaren we niet langer dan nodig (AVG).

De dagelijkse job ``levendmonument-opschonen`` roept ``verwijder_ongebruikte_accounts``
aan met de EIGENAAR-verbinding. Een account wordt alleen verwijderd als ALLES klopt:

- rol ``visitor`` (nooit een curator, beheerder, docent of leerling);
- niet geverifieerd en nooit ingelogd: de link is nooit gebruikt;
- ouder dan 7 dagen (de link zelf verloopt na 15 minuten);
- nergens naar verwezen: geen verhaal, klas, archiefexport of docentaanvraag.
  Die verwijzingen staan op ``ON DELETE SET NULL``; zonder deze controle zou een
  verhaal stil zijn inzender kwijtraken.

Inloglinks van zo'n account verdwijnen mee (``ON DELETE CASCADE``).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import Delete, delete, exists
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.foundation_content import (
    FoundationArchiveExport,
    FoundationContent,
    FoundationTeacherApplication,
    PortalRole,
    PortalUser,
    StudyCollection,
)

#: Zo lang mag een account met een nooit gebruikte link blijven staan.
ONGEBRUIKT_NA = timedelta(days=7)


def ongebruikte_accounts_stmt(nu: datetime, tenant_id: int | None = None) -> Delete:
    """De DELETE voor ongebruikte vertelleraccounts (zie de moduletekst voor de regels)."""
    voorwaarden = [
        PortalUser.role == PortalRole.VISITOR,
        PortalUser.is_verified.is_(False),
        PortalUser.email_verified.is_(False),
        PortalUser.last_login_at.is_(None),
        PortalUser.created_at < nu - ONGEBRUIKT_NA,
        ~exists().where(FoundationContent.uploader_id == PortalUser.id),
        ~exists().where(StudyCollection.owner_portal_user_id == PortalUser.id),
        ~exists().where(FoundationArchiveExport.created_by_portal_user_id == PortalUser.id),
        ~exists().where(FoundationTeacherApplication.portal_user_id == PortalUser.id),
        ~exists().where(FoundationTeacherApplication.decided_by_portal_user_id == PortalUser.id),
    ]
    if tenant_id is not None:
        voorwaarden.append(PortalUser.tenant_id == tenant_id)
    return delete(PortalUser).where(*voorwaarden)


async def verwijder_ongebruikte_accounts(
    sessie: AsyncSession, nu: datetime, tenant_id: int | None = None
) -> int:
    """Verwijder ongebruikte vertelleraccounts; geeft het aantal verwijderde accounts."""
    resultaat = await sessie.execute(ongebruikte_accounts_stmt(nu, tenant_id))
    return int(getattr(resultaat, "rowcount", 0) or 0)
