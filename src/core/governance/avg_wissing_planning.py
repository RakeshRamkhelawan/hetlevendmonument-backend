"""Plannen en intrekken van een AVG-wissing (art. 17): 30 dagen wachttijd, in te trekken.

Besluit Rakesh 2026-10-12. Een wissingsaanvraag doet NIETS onomkeerbaars: de betrokkene wordt
inactief (kan niet inloggen) en krijgt `deletion_scheduled_for = nu + 30 dagen`. Pas na die datum
plant de dagelijkse planner (`src/core/jobs/avg_purge_job.py`) de purge in. Tot dan kan de
beheerder de aanvraag intrekken.

De toestand staat in de database, niet in een Dramatiq-vertraging: een bericht dat 30 dagen in
Redis wacht overleeft geen herstart of leegmaken van de broker. Er is geen migratie nodig; de
kolommen `users.deleted_at` en `users.deletion_scheduled_for` bestonden al.

Herkenning van "door deze aanvraag inactief gemaakt": `deleted_at + 30 dagen == deletion_scheduled_for`.
Wie al inactief was (of om een andere reden `deleted_at` heeft) blijft bij intrekken ongemoeid, zodat
een intrekking nooit iemand heractiveert die de beheerder bewust had uitgezet.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.session import get_db_session
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.governance.audit import AuditService
from src.core.governance.models import AuditLog
from src.core.models.rbac_models import Tenant, User
from src.core.shared.tenant_beheerders import AUDITACTIE_TENANT_ZONDER_BEHEERDER
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

WACHTTIJD = timedelta(days=30)


def plan_gebruiker_wissing(
    user: User, nu: datetime, gepland: datetime | None = None
) -> datetime:
    """Plan de wissing van een gebruiker; geeft de datum van de purge terug.

    Idempotent: een tweede aanvraag houdt de eerste termijn (de datum schuift niet op). `gepland`
    legt de termijn vast (een tweede delete-all neemt de termijn van de eerste over).
    """
    if user.deletion_scheduled_for is not None:
        return user.deletion_scheduled_for
    gepland = gepland or nu + WACHTTIJD
    if user.is_active:
        user.is_active = False
        # Zo blijft `deleted_at + 30 dagen == deletion_scheduled_for` ook bij een overgenomen termijn.
        user.deleted_at = gepland - WACHTTIJD
    user.deletion_scheduled_for = gepland
    return gepland


def is_door_aanvraag_inactief(user: User) -> bool:
    """Is deze gebruiker door een wissingsaanvraag inactief gemaakt (en niet om een andere reden)?"""
    if user.deleted_at is None or user.deletion_scheduled_for is None:
        return False
    return user.deleted_at + WACHTTIJD == user.deletion_scheduled_for


def termijn_is_verstreken(user: User, nu: datetime) -> bool:
    return user.deletion_scheduled_for is not None and user.deletion_scheduled_for <= nu


def trek_gebruiker_wissing_in(user: User) -> bool:
    """Trek de wissing in: weer actief als de aanvraag hem inactief maakte. False: niets te doen."""
    if user.deletion_scheduled_for is None:
        return False
    if is_door_aanvraag_inactief(user):
        user.is_active = True
        user.deleted_at = None
    user.deletion_scheduled_for = None
    return True


async def eigen_gebruiker(db: AsyncSession, tenant_id: int, user_id: int) -> User | None:
    """De gebruiker, alleen als hij in DEZE tenant zit (anders None: de aanroeper geeft 404)."""
    resultaat = await db.execute(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    return resultaat.scalar_one_or_none()


async def gebruikers_met_geplande_wissing(db: AsyncSession, tenant_id: int) -> list[User]:
    resultaat = await db.execute(
        select(User).where(User.tenant_id == tenant_id, User.deletion_scheduled_for.is_not(None))
    )
    return list(resultaat.scalars().all())


async def activeer_tenant(db: AsyncSession, tenant_id: int) -> None:
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if tenant is not None:
        tenant.is_active = True


async def meld_tenant_zonder_beheerder(tenant_id: int) -> None:
    """WARNING plus auditregel: de tenant heeft na deze AVG-wissing geen actieve beheerder meer.

    Alleen het tenant-id, geen persoonsgegevens. Best-effort: de wissing zelf is al geregeld.
    """
    logger.warning(
        "%s: tenant %s heeft na een AVG-wissing geen actieve beheerder meer; geef de klant een "
        "nieuwe beheerder",
        AUDITACTIE_TENANT_ZONDER_BEHEERDER,
        tenant_id,
    )
    async with get_db_session() as audit_db:
        with TenantFilterBypass():
            async with best_effort("tenant zonder beheerder (AVG)", db_session=audit_db):
                await AuditService.log_action(
                    tenant_id=tenant_id,
                    action=AUDITACTIE_TENANT_ZONDER_BEHEERDER,
                    resource=f"tenant:{tenant_id}",
                    user_id=None,
                    details={"tenant_id": tenant_id, "reden": "avg_wissing_laatste_beheerder"},
                    session=audit_db,
                    event_type="gdpr_purge",
                    threat_level="warning",
                    client_ip="system",
                    endpoint="gdpr_purge_actor",
                    description=(
                        f"Tenant {tenant_id} heeft na een AVG-wissing geen actieve beheerder meer"
                    ),
                )


async def alle_delete_all_termijnen(db: AsyncSession, tenant_id: int) -> set[datetime]:
    """Elke termijn die ooit door een tenantbrede wissing (delete-all) is gezet, ingetrokken of niet.

    De export-eerst-wacht van de purge (`actors/gdpr_purge.py`) hangt hieraan en NIET aan de laatste
    aanvraag: een tweede delete-all na het verlopen van de eerste zet een nieuwe termijn, en de
    gebruikers van de eerste groep houden hun oude termijn. Met alleen de laatste termijn viel die
    groep uit de wachtregel en werd zonder export gewist (Gate 2, 2026-10-13). Een ingetrokken
    termijn schaadt niet: de gebruikers die erbij hoorden hebben dan geen termijn meer.
    """
    resultaat = await db.execute(
        select(AuditLog.details).where(
            AuditLog.tenant_id == tenant_id, AuditLog.action == "gdpr_delete_all"
        )
    )
    termijnen: set[datetime] = set()
    for details in resultaat.scalars().all():
        datum = details.get("scheduled_purge") if isinstance(details, dict) else None
        if isinstance(datum, str):
            termijnen.add(datetime.fromisoformat(datum))
    return termijnen


async def lopende_delete_all(db: AsyncSession, tenant_id: int) -> tuple[datetime, list[str]] | None:
    """De lopende tenantbrede wissing: (termijn, ids van de workflows die hij uitzette), of None.

    De groep van een delete-all is exact de verzameling gebruikers met DEZELFDE termijn als in zijn
    auditregel; een losse medewerker-wissing heeft een eigen termijn en hoort er niet bij. Een tweede
    delete-all neemt de eerste termijn over, dus de ids van alle regels met die termijn tellen mee.
    """
    resultaat = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action.in_(("gdpr_delete_all", "gdpr_delete_all_revoked")),
        )
        .order_by(AuditLog.id.desc())
    )
    regels = list(resultaat.scalars().all())
    if not regels or regels[0].action != "gdpr_delete_all":
        return None  # nooit aangevraagd, of al ingetrokken
    eerste = regels[0].details
    datum = eerste.get("scheduled_purge") if isinstance(eerste, dict) else None
    if not isinstance(datum, str):
        return None
    ids: list[str] = []
    for regel in regels:
        if regel.action != "gdpr_delete_all" or not isinstance(regel.details, dict):
            break  # alleen de aaneengesloten aanvragen sinds de laatste intrekking
        if regel.details.get("scheduled_purge") == datum:
            lijst = regel.details.get("deactivated_workflow_ids", [])
            if isinstance(lijst, list):
                ids.extend(str(i) for i in lijst)
    return datetime.fromisoformat(datum), ids
