"""Elke dag een melding aan HR als een termijn nadert -- HR-pilot dag 4.

`signaleer_hr_termijnen` kijkt per tenant naar de OPEN termijnen (`hr_deadlines`) en zet voor elke
termijn die binnen 14 dagen valt, of al voorbij is, een melding in de meldingenlijst van de app
(`notifications`, dezelfde tabel die `GET /api/v1/notifications` uitleest) voor elke gebruiker die
`hr:read` heeft. Dat is ALLES wat de taak doet:

- **Alleen signaleren.** De taak verandert niets aan een termijnrij, wijst niets toe en beslist
  niets (ADR-039). Een test vergelijkt de rijen voor en na.
- **Geen omschrijving, geen e-mailadres.** De melding noemt de soort termijn, de datum en de
  INITIALEN van de medewerker. Een omschrijving komt er nooit in; bij verzuim bestaat die ook
  niet (verzuim is een gezondheidsgegeven).
- **Eenmaal per termijn per gebruiker per dag.** (Twee gelijktijdige runs wachten op een advisory
  lock per tenant; die is NIET onder gelijktijdigheid getest, alleen na elkaar.) Elke melding draagt een sleutel
  `hr_termijn:<regel>:<termijn>:<datum van de run>`; bestaat die voor deze gebruiker al, dan wordt
  er niets bijgezet. Een tweede run op dezelfde dag is dus onschadelijk; de volgende dag komt de
  herinnering terug zolang de termijn open staat.
- **Tenant.** De run werkt over alle tenants heen; alleen de selectie van de tenants met een open
  termijn gaat langs `TenantFilterBypass`. Daarna wordt elke tenant verwerkt binnen
  `adopt_tenant` (dezelfde werkwijze als `ROIService`), zodat RLS onder de applicatierol niets
  stil weglaat. De `tenant_id` komt uit de database, nooit uit een verzoek.
- **Ontvangers.** Wie `hr:read` heeft, bepaalt `RBACService.user_has_permission`: dezelfde
  regel als de routes (`*:read` telt niet voor `hr`, de beheerder via `*:*` wel).
- **Geen e-mail.** Alleen in de app.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone

from src.core.tasks.dramatiq_broker import workflow_actor
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.bypass_session import adopt_tenant
from src.core.database.session import get_db_session
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.models.hr_deadline_models import HRDeadline
from src.core.models.rbac_models import User
from src.core.repositories.hr_deadlines_repository import HRDeadlinesRepository, UpcomingItem
from src.core.services.rbac_service import RBACService
from src.core.tasks.eigen_loop import SessieFabriek, draai_in_eigen_loop
from src.domains.notifications.models import Notification

logger = logging.getLogger(__name__)

#: Een termijn die binnen zoveel dagen valt (of al voorbij is) geeft een melding.
SIGNAAL_VENSTER_DAGEN = 14
MELDING_TYPE = "hr_termijn"
#: Eerste getal van de advisory lock; het tweede is de tenant (twee sleutels van elk 32 bit).
LOCK_RUIMTE = 7104
#: Waar een klik op de melding naartoe gaat.
MELDING_LINK = "/personeel"


def _initialen(email: str) -> str:
    """`anna.jansen@x.nl` -> `A.J.`: genoeg om de medewerker te herkennen, geen naam of adres."""
    delen = [d for d in re.split(r"[._\-+]", email.split("@", 1)[0]) if d[:1].isalpha()]
    if not delen:
        return "?"
    return "".join(f"{d[0].upper()}." for d in delen)


def _sleutel(item: UpcomingItem, vandaag: date) -> str:
    return f"{MELDING_TYPE}:{item.deadline_id}:{item.label}:{vandaag.isoformat()}"


async def _tenants_met_open_termijnen(sessie: AsyncSession) -> list[int]:
    # Cross-tenant op de enige plek waar dat moet: een worker heeft geen verzoek en dus geen
    # tenant. Alleen de tenantnummers worden gelezen; verwerken gebeurt per tenant.
    with TenantFilterBypass():
        resultaat = await sessie.execute(
            select(HRDeadline.tenant_id).where(HRDeadline.status == "open").distinct()
        )
    tenants = sorted(int(t) for (t,) in resultaat.all())
    await sessie.rollback()
    return tenants


async def _ontvangers(sessie: AsyncSession, tenant_id: int) -> list[int]:
    """De actieve gebruikers van deze tenant met `hr:read`."""
    kandidaten = (
        (
            await sessie.execute(
                select(User.id).where(
                    User.tenant_id == tenant_id,
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    rbac = RBACService(sessie)
    return [
        int(uid)
        for uid in kandidaten
        if await rbac.user_has_permission(int(uid), "hr:read", tenant_id)
    ]


async def _bestaande_sleutels(
    sessie: AsyncSession, tenant_id: int, vandaag: date
) -> set[tuple[int, str]]:
    rijen = await sessie.execute(
        select(Notification.user_id, Notification.data["key"].astext).where(
            Notification.tenant_id == tenant_id,
            Notification.type == MELDING_TYPE,
            Notification.data["key"].astext.like(f"%:{vandaag.isoformat()}"),
        )
    )
    return {(int(user_id), str(sleutel)) for user_id, sleutel in rijen.all()}


def _melding(
    tenant_id: int, user_id: int, item: UpcomingItem, initialen: str, sleutel: str
) -> Notification:
    datum = item.datum.strftime("%d-%m-%Y")
    titel = f"Termijn te laat: {item.label}" if item.te_laat else f"Termijn nadert: {item.label}"
    return Notification(
        tenant_id=tenant_id,
        user_id=user_id,
        type=MELDING_TYPE,
        title=titel,
        # Nooit de omschrijving van de regel en nooit het e-mailadres: alleen initialen.
        body=f"{initialen} - uiterlijk {datum}. {item.toelichting}",
        data={
            "link": MELDING_LINK,
            "key": sleutel,
            "deadline_id": item.deadline_id,
            "kind": item.kind,
            "label": item.label,
            "date": item.datum.isoformat(),
            "te_laat": item.te_laat,
        },
        channel="in_app",
    )


async def _signaleer_tenant(sessie: AsyncSession, tenant_id: int, vandaag: date) -> int:
    """Meldingen voor een tenant zetten en committen; het aantal nieuwe meldingen."""
    async with adopt_tenant(sessie, tenant_id):
        # Een advisory lock per tenant, tot de commit: twee gelijktijdige runs (de planner naast
        # een handmatige `.send()`) wachten op elkaar en zien daarna elkaars meldingen. Zonder
        # lock lezen beide "bestaat nog niet" en melden ze dubbel. Geen migratie nodig.
        await sessie.execute(
            text("SELECT pg_advisory_xact_lock(:ruimte, :tenant)"),
            {"ruimte": LOCK_RUIMTE, "tenant": tenant_id},
        )
        items = await HRDeadlinesRepository(sessie).upcoming(
            tenant_id, vandaag, venster_dagen=SIGNAAL_VENSTER_DAGEN
        )
        if not items:
            return 0
        ontvangers = await _ontvangers(sessie, tenant_id)
        if not ontvangers:
            return 0
        bestaand = await _bestaande_sleutels(sessie, tenant_id, vandaag)
        namen = {
            int(uid): _initialen(email)
            for uid, email in (
                await sessie.execute(select(User.id, User.email).where(User.tenant_id == tenant_id))
            ).all()
        }
        nieuw = 0
        for item in items:
            sleutel = _sleutel(item, vandaag)
            initialen = namen.get(item.employee_id, "?")
            for user_id in ontvangers:
                if (user_id, sleutel) in bestaand:
                    continue
                # De betrokken medewerker zelf krijgt de melding niet.
                if user_id == item.employee_id:
                    continue
                sessie.add(_melding(tenant_id, user_id, item, initialen, sleutel))
                nieuw += 1
        await sessie.commit()
        return nieuw


async def signaleer_hr_termijnen_async(
    sessie_fabriek: SessieFabriek | None = None, nu: datetime | None = None
) -> int:
    """Signaleer de naderende en te late HR-termijnen; het totaal aantal nieuwe meldingen.

    `nu` is een parameter zodat de klok in een test vast staat; `None` is de echte klok.
    """
    vandaag = (nu or datetime.now(timezone.utc)).date()
    fabriek = sessie_fabriek or get_db_session
    totaal = 0
    async with fabriek() as sessie:
        for tenant_id in await _tenants_met_open_termijnen(sessie):
            try:
                totaal += await _signaleer_tenant(sessie, tenant_id, vandaag)
            except SQLAlchemyError:
                logger.error(
                    "hr termijnen signaleren: tenant %s niet verwerkt (databasefout)",
                    tenant_id,
                    exc_info=True,
                )
                await sessie.rollback()
    if totaal:
        logger.info("hr termijnen signaleren: %d meldingen gezet", totaal)
    return totaal


@workflow_actor(
    queue_name="default",
    max_retries=0,
    time_limit=300_000,
    actor_name="signaleer_hr_termijnen",
)
def signaleer_hr_termijnen() -> None:
    """Dramatiq-ingang: een keer per dag door de scheduler gestart.

    `max_retries=0`: de volgende dagrun pakt wat is blijven liggen; de sleutel per termijn en dag
    maakt een herhaling onschadelijk.
    """

    async def _taak(fabriek: SessieFabriek) -> None:
        await signaleer_hr_termijnen_async(sessie_fabriek=fabriek)

    draai_in_eigen_loop(_taak)
