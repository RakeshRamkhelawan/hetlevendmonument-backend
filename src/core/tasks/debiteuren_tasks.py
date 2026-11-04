"""De brief gaat echt de deur uit -- debiteuren Keten B dag 2.

`verstuur_klare_berichten` leest de uitgaande berichten die een mens heeft goedgekeurd
(`outgoing_messages`, status `klaar`) en verstuurt ze via de mailservice. Het is de tweede helft
van het outbox-patroon: de goedkeuring zet een rij klaar, deze actor verstuurt hem.

**Eenmaligheid.** Per bericht een eigen korte transactie: de rij wordt vergrendeld met
`SELECT ... FOR UPDATE SKIP LOCKED`, verstuurd, bijgewerkt en gecommit. Een tweede run die
gelijktijdig draait slaat een vergrendelde rij over, en ziet na de commit de nieuwe status. Bij
een crash tussen versturen en commit blijft de rij `klaar`: dan kan de brief dubbel gaan
(at-least-once), niet nooit. Dat is bewust de veilige kant voor een betalingsherinnering.

**Tenant.** De run werkt over alle tenants heen (alleen de selectie van kandidaten gaat langs
`TenantFilterBypass`). Elk bericht wordt verwerkt binnen `adopt_tenant` met de tenant van de rij
zelf; de `tenant_id` komt dus uit de database en nooit uit een verzoek.

**Logboek.** Per verzonden of mislukt bericht een auditregel, NA de commit van de statuswijziging
en in `best_effort`: een kapot logboek blokkeert de verzending niet. De regel noemt het
bericht-id en de uitkomst, nooit ontvanger, tekst of foutboodschap van de server.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.core.tasks.dramatiq_broker import workflow_actor
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.core.database.bypass_session import adopt_tenant
from src.core.database.session import get_db_session
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.governance.audit import AuditService
from src.core.models.outgoing_message_models import (
    FOUTREDEN_GEANNULEERD_BETAALD,
    FOUTREDEN_GEANNULEERD_ONBEKEND,
    MAX_POGINGEN,  # noqa: F401 -- blijft hier te importeren: `MAX_POGINGEN` stond altijd in deze module
    OutgoingMessage,
)
from src.core.models.rbac_models import Tenant, User
from src.core.models.receivable_models import Receivable
from src.core.noodstop.guard import klant_staat_stil
from src.core.services.rbac_service import RBACService
from src.domains.notifications.models import Notification
from src.core.services.email import EmailMessage, get_email_service
from src.core.tasks.eigen_loop import SessieFabriek, draai_in_eigen_loop
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

#: Statussen waarin een vordering nog een brief mag krijgen. Een betaalde vordering krijgt er geen meer.
_VERZENDBARE_STATUSSEN = ("open", "herinnerd", "geescaleerd")

#: Een vaste tekst: de foutboodschap van een mailserver kan een inlognaam of wachtwoord noemen en
#: mag niet in een kolom komen die de gebruiker te zien krijgt.
FOUTREDEN_VERZENDEN = "Verzenden mislukt: de mailserver nam het bericht niet aan."
FOUTREDEN_ONVERWACHT = "Verzenden mislukt door een onverwachte fout ({soort})."

#: Na zoveel dagen zonder betaling vanaf `herinnerd_op` wordt een dossier `geescaleerd`. De
#: grens is inclusief: op dag 14 zelf escaleert het dossier.
#: Gelijk aan `governance.debiteuren_instellingen.STANDAARD_ESCALATIE_NA_DAGEN` (een test bewaakt dat). Hier een eigen
#: getal en geen import: een import van governance op moduleniveau tilde de koppeling agent_runtime -> governance boven
#: het plafond van `test_dsm006_ar_governance_fan_out.py`.
ESCALATIE_NA_DAGEN = 14

#: De melding bij een escalatie: type in de meldingenlijst en waar een klik naartoe gaat.
MELDING_TYPE = "debiteuren_escalatie"
MELDING_LINK = "/debiteuren"

def _is_te_verzenden() -> ColumnElement[bool]:
    return or_(
        OutgoingMessage.status == "klaar",
        and_(OutgoingMessage.status == "mislukt", OutgoingMessage.pogingen < MAX_POGINGEN),
    )


async def _kandidaten(sessie: AsyncSession) -> list[tuple[int, int, int]]:
    """(id, tenant_id, pogingen) van alle berichten die een poging verdienen, over alle tenants."""
    # Cross-tenant op de enige plek waar dat moet: een worker heeft geen verzoek en dus geen
    # tenant. Alleen id/tenant/pogingen worden gelezen; verwerken gebeurt per rij onder de
    # tenant van die rij.
    with TenantFilterBypass():
        resultaat = await sessie.execute(
            select(OutgoingMessage.id, OutgoingMessage.tenant_id, OutgoingMessage.pogingen)
            .where(_is_te_verzenden())
            .order_by(OutgoingMessage.id)
        )
    rijen = [(int(r[0]), int(r[1]), int(r[2])) for r in resultaat.all()]
    # Sluit de leestransactie, zodat de volgende begint met de tenantcontext van de rij.
    await sessie.rollback()
    return rijen


async def _verstuur(bericht: OutgoingMessage) -> str | None:
    """Verstuurt een bericht. Geeft None bij succes, anders de (geheimvrije) foutreden."""
    dienst = get_email_service()
    try:
        gelukt = await dienst.send(
            EmailMessage(to=bericht.recipient, subject=bericht.subject, body=bericht.body)
        )
    except Exception as exc:  # noqa: BLE001 - een onverwachte fout telt als mislukte poging
        # Bewust breed: een willekeurige fout bij EEN bericht mag de run voor de rest niet
        # stoppen en moet `pogingen` laten oplopen. Gelogd met stacktrace; de soort komt in de
        # foutreden, de tekst niet (kan een inlognaam of wachtwoord bevatten).
        logger.error(
            "debiteuren verzenden: bericht %s mislukt: %s",
            bericht.id,
            type(exc).__name__,
            exc_info=True,
        )
        return FOUTREDEN_ONVERWACHT.format(soort=type(exc).__name__)
    return None if gelukt else FOUTREDEN_VERZENDEN


async def _markeer_herinnerd(sessie: AsyncSession, bericht: OutgoingMessage) -> None:
    """De vordering van een VERZONDEN brief wordt `herinnerd`, met de verzendtijd als klok.

    Dit is de enige plek die `herinnerd` zet: de PATCH-route en de repository weigeren het, en
    klaarzetten (`send_payment_reminder`) laat de status staan. Zo telt de 14-dagenklok van de
    opvolging pas vanaf een brief die aantoonbaar weg is. Alleen `open` wordt `herinnerd`: een
    aanmaning op een `geescaleerd` dossier laat de status staan (anders escaleert de opvolging
    hem na 14 dagen opnieuw), en een inmiddels betaalde factuur blijft betaald.
    """
    if bericht.receivable_id is None:
        return
    rij = (
        await sessie.execute(
            select(Receivable)
            .where(
                Receivable.id == bericht.receivable_id,
                Receivable.tenant_id == bericht.tenant_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if rij is not None and rij.status == "open":
        rij.status = "herinnerd"
        rij.herinnerd_op = bericht.verzonden_op


async def _annuleer_als_niet_meer_open(sessie: AsyncSession, bericht: OutgoingMessage) -> bool:
    """Annuleer het bericht als zijn vordering betaald is (of niet bestaat binnen de tenant). True = geannuleerd.

    Een geannuleerd bericht is `mislukt` met `pogingen = MAX_POGINGEN` en een foutreden die met "Geannuleerd:" begint:
    een eigen status vraagt een migratie (CHECK), dus dit is de afgesproken vorm. De aanroeper commit.
    """
    if bericht.receivable_id is None:
        return False
    rij = (
        await sessie.execute(
            select(Receivable)
            .where(
                Receivable.id == bericht.receivable_id,
                Receivable.tenant_id == bericht.tenant_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if rij is not None and rij.status in _VERZENDBARE_STATUSSEN:
        return False
    bericht.status = "mislukt"
    bericht.pogingen = MAX_POGINGEN
    bericht.foutreden = (
        FOUTREDEN_GEANNULEERD_ONBEKEND if rij is None else FOUTREDEN_GEANNULEERD_BETAALD
    )
    return True


async def _verwerk(
    sessie: AsyncSession, bericht_id: int, tenant_id: int, gezien_pogingen: int
) -> tuple[str, int] | None:
    """Een bericht: claimen, versturen, status bijwerken, committen. None als overgeslagen."""
    async with adopt_tenant(sessie, tenant_id):
        # Het slot is de claim: een gelijktijdige run slaat deze rij over (SKIP LOCKED). De
        # voorwaarde op `pogingen` voorkomt dat een run een rij die net door de ander is
        # mislukt meteen nog eens probeert.
        resultaat = await sessie.execute(
            select(OutgoingMessage)
            .where(
                OutgoingMessage.id == bericht_id,
                OutgoingMessage.tenant_id == tenant_id,
                OutgoingMessage.pogingen == gezien_pogingen,
                _is_te_verzenden(),
            )
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        bericht = resultaat.scalar_one_or_none()
        if bericht is None:
            await sessie.rollback()
            return None

        # Vlak voor het versturen de vordering opnieuw lezen, onder een rijslot in DEZELFDE transactie: een betaling
        # tussen goedkeuren en versturen mag geen brief meer opleveren (acceptatie 2026-10-19). Een bericht zonder
        # vordering (SET NULL) blijft zoals het was; wijst het naar een vordering die niet binnen de tenant bestaat,
        # dan gaat er niets uit.
        geannuleerd = await _annuleer_als_niet_meer_open(sessie, bericht)
        if geannuleerd:
            await sessie.commit()
            return "geannuleerd", tenant_id

        foutreden = await _verstuur(bericht)
        bericht.pogingen = bericht.pogingen + 1
        if foutreden is None:
            bericht.status = "verzonden"
            bericht.verzonden_op = datetime.now(timezone.utc)
            bericht.foutreden = None
            await _markeer_herinnerd(sessie, bericht)
        else:
            bericht.status = "mislukt"
            bericht.foutreden = foutreden
        uitkomst = bericht.status
        await sessie.commit()

    return uitkomst, tenant_id


async def _log_uitkomst(
    sessie: AsyncSession, bericht_id: int, tenant_id: int, uitkomst: str
) -> None:
    """Auditregel in de tenant van het bericht; faalt dit, dan is de verzending al gebeurd."""
    async with adopt_tenant(sessie, tenant_id):
        async with best_effort("debiteuren verzenden audit", db_session=sessie):
            await AuditService.log_action(
                tenant_id=tenant_id,
                action=f"debiteuren_bericht_{uitkomst}",
                resource=f"outgoing_message:{bericht_id}",
                details={"bericht_id": bericht_id, "status": uitkomst},
                session=sessie,
                endpoint="worker:verstuur_klare_berichten",
            )
            await sessie.commit()


async def verstuur_klare_berichten_async(sessie_fabriek: SessieFabriek | None = None) -> None:
    """Verstuurt alle klare berichten (en mislukte met pogingen over), een voor een."""
    fabriek = sessie_fabriek or get_db_session
    async with fabriek() as sessie:
        kandidaten = await _kandidaten(sessie)
        verzonden = mislukt = geannuleerd = overgeslagen = 0
        for bericht_id, tenant_id, pogingen in kandidaten:
            # NOODSTOP PER KLANT (ADR-036 OP-03): deze actor is een deur -- hij stuurt echt een
            # brief naar een debiteur. Per bericht gecontroleerd, vlak voor het claimen, zodat een
            # stop die middenin een run valt de rest van die run tegenhoudt. Het bericht blijft
            # `klaar` (geen poging, niet `mislukt`): na het opheffen van de stop gaat het alsnog weg.
            # Fail-closed: een stand die niet te lezen is telt als stil.
            if await klant_staat_stil(tenant_id):
                overgeslagen += 1
                continue
            try:
                gedaan = await _verwerk(sessie, bericht_id, tenant_id, pogingen)
            except SQLAlchemyError:
                logger.error(
                    "debiteuren verzenden: bericht %s niet verwerkt (databasefout)",
                    bericht_id,
                    exc_info=True,
                )
                await sessie.rollback()
                continue
            if gedaan is None:
                continue
            uitkomst, tenant = gedaan
            if uitkomst == "verzonden":
                verzonden += 1
            elif uitkomst == "geannuleerd":
                geannuleerd += 1
            else:
                mislukt += 1
            await _log_uitkomst(sessie, bericht_id, tenant, uitkomst)
    if verzonden or mislukt or geannuleerd:
        logger.info(
            "debiteuren verzenden: %d verzonden, %d mislukt, %d geannuleerd",
            verzonden,
            mislukt,
            geannuleerd,
        )
    if overgeslagen:
        logger.warning("debiteuren verzenden: %d berichten overgeslagen (noodstop)", overgeslagen)


@workflow_actor(
    queue_name="default",
    max_retries=0,
    time_limit=300_000,
    actor_name="verstuur_klare_berichten",
)
def verstuur_klare_berichten() -> None:
    """Dramatiq-ingang: elke minuut door de scheduler gestart.

    `max_retries=0`: de volgende minuutrun is de nieuwe poging, en `pogingen` op de rij telt
    ze. Een Dramatiq-herhaling zou daar dubbel overheen lopen.
    """
    draai_in_eigen_loop(verstuur_klare_berichten_async)


def _er_is_een_verzonden_brief() -> ColumnElement[bool]:
    """Er bestaat voor deze vordering een bericht dat echt verzonden is.

    De vangrail voor `herinnerd` dossiers zonder brief: rijen van voor wfb-dag1 stap 2, toen de
    status nog met de hand (of door een workflow met een token) gezet kon worden. Zo'n dossier
    escaleert niet; het wettelijke vervolg rust dan op een brief die niet aantoonbaar weg is.
    """
    return exists().where(
        OutgoingMessage.receivable_id == Receivable.id,
        OutgoingMessage.tenant_id == Receivable.tenant_id,
        OutgoingMessage.status == "verzonden",
    )


def _als_utc(moment: datetime) -> datetime:
    """SQLite geeft tijdstempels zonder zone terug; in de database staat altijd UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def _termijn_uit_settings(settings: object) -> int:
    """De termijn uit `tenants.settings`; lazy via importlib, zie `ESCALATIE_NA_DAGEN`."""
    import importlib

    instellingen = importlib.import_module("src.core.governance.debiteuren_instellingen")
    termijn: int = instellingen.escalatie_na_dagen_uit_settings(settings)
    return termijn


async def _escalatiekandidaten(
    sessie: AsyncSession, nu: datetime
) -> list[tuple[int, int, datetime, int]]:
    """(id, tenant_id, grens, termijn) van `herinnerd` dossiers die op of voor hun EIGEN grens zijn herinnerd.

    De termijn is die van de tenant (`escalatie_na_dagen` in `tenants.settings`, standaard 14), de grens is
    `nu - termijn`; elke tenant wordt dus op zijn eigen termijn beoordeeld.
    """
    # Cross-tenant op de enige plek waar dat moet (zie `_kandidaten`); verwerken gebeurt per rij
    # onder de tenant van die rij. Een ontbrekende `herinnerd_op` valt terug op `created_at`.
    with TenantFilterBypass():
        resultaat = await sessie.execute(
            select(
                Receivable.id,
                Receivable.tenant_id,
                Receivable.herinnerd_op,
                Receivable.created_at,
            )
            .where(Receivable.status == "herinnerd", _er_is_een_verzonden_brief())
            .order_by(Receivable.id)
        )
        ruwe_rijen = resultaat.all()
        tenant_ids = {int(rij[1]) for rij in ruwe_rijen}
        settings: dict[int, object] = {}
        if tenant_ids:
            tenants = await sessie.execute(
                select(Tenant.id, Tenant.settings).where(Tenant.id.in_(tenant_ids))
            )
            settings = {int(tid): waarde for tid, waarde in tenants.all()}
    rijen: list[tuple[int, int, datetime, int]] = []
    for rij_id, tenant_id, herinnerd_op, created_at in ruwe_rijen:
        termijn = _termijn_uit_settings(settings.get(int(tenant_id)))
        grens = nu - timedelta(days=termijn)
        moment = herinnerd_op or created_at
        if moment is not None and _als_utc(moment) <= grens:
            rijen.append((int(rij_id), int(tenant_id), grens, termijn))
    await sessie.rollback()
    return rijen


async def _escaleer(
    sessie: AsyncSession, receivable_id: int, tenant_id: int, grens: datetime
) -> bool:
    """Een dossier escaleren en committen. False als het inmiddels niet meer aan de beurt is."""
    async with adopt_tenant(sessie, tenant_id):
        resultaat = await sessie.execute(
            select(Receivable)
            .where(
                Receivable.id == receivable_id,
                Receivable.tenant_id == tenant_id,
                Receivable.status == "herinnerd",
                _er_is_een_verzonden_brief(),
            )
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        rij = resultaat.scalar_one_or_none()
        moment = None if rij is None else (rij.herinnerd_op or rij.created_at)
        if rij is None or moment is None or _als_utc(moment) > grens:
            await sessie.rollback()
            return False
        rij.status = "geescaleerd"
        await sessie.commit()
    return True


async def _log_escalatie(sessie: AsyncSession, receivable_id: int, tenant_id: int) -> None:
    """Auditregel in de tenant van het dossier; zonder naam of e-mail van de debiteur."""
    async with adopt_tenant(sessie, tenant_id):
        async with best_effort("debiteuren opvolgen audit", db_session=sessie):
            await AuditService.log_action(
                tenant_id=tenant_id,
                action="debiteuren_dossier_geescaleerd",
                resource=f"receivable:{receivable_id}",
                details={"receivable_id": receivable_id, "status": "geescaleerd"},
                session=sessie,
                endpoint="worker:volg_debiteuren_op",
            )
            await sessie.commit()


async def _ontvangers_van_voorstellen(sessie: AsyncSession, tenant_id: int) -> list[int]:
    """De actieve gebruikers van deze tenant met `receivables:propose` (zoals `hr_termijn_tasks._ontvangers`)."""
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
        if await rbac.user_has_permission(int(uid), "receivables:propose", tenant_id)
    ]


async def _meld_escalatie(
    sessie: AsyncSession, receivable_id: int, tenant_id: int, termijn: int
) -> None:
    """Zet een melding in de app voor de medewerkers die een aanmaning mogen voorstellen (B3, 2026-10-20).

    Alleen intern: er komt geen `outgoing_messages`-rij en geen mail, dus er gaat niets naar de debiteur. De melding
    noemt factuurnummer, naam van de debiteur en de termijn, geen e-mailadres. Best-effort: een kapotte melding
    draait de al vastgelegde escalatie niet terug.
    """
    async with adopt_tenant(sessie, tenant_id):
        async with best_effort("debiteuren escalatie melding", db_session=sessie):
            rij = (
                await sessie.execute(
                    select(Receivable.invoice_number, Receivable.customer_name).where(
                        Receivable.id == receivable_id, Receivable.tenant_id == tenant_id
                    )
                )
            ).one_or_none()
            if rij is None:
                return
            factuur, naam = rij
            for user_id in await _ontvangers_van_voorstellen(sessie, tenant_id):
                sessie.add(
                    Notification(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        type=MELDING_TYPE,
                        title=f"Factuur {factuur} is geescaleerd",
                        body=(
                            f"Factuur {factuur} van {naam} is na {termijn} dagen niet betaald en is "
                            "geescaleerd. Stel zo nodig een aanmaning voor."
                        ),
                        data={"link": MELDING_LINK, "receivable_id": receivable_id},
                        channel="in_app",
                    )
                )
            await sessie.commit()


async def volg_debiteuren_op_async(
    sessie_fabriek: SessieFabriek | None = None, nu: datetime | None = None
) -> None:
    """Escaleert `herinnerd` dossiers die de eigen termijn van hun tenant of langer niet zijn betaald.

    De termijn is `escalatie_na_dagen` in `tenants.settings` (standaard `ESCALATIE_NA_DAGEN`, 14). Escaleren
    verstuurt niets: een aanmaning loopt weer langs de goedkeuring van een mens. `nu` is een parameter zodat de
    klok in een test vast staat; `None` is de echte klok.
    """
    klok = nu or datetime.now(timezone.utc)
    fabriek = sessie_fabriek or get_db_session
    geescaleerd = overgeslagen = 0
    async with fabriek() as sessie:
        for receivable_id, tenant_id, grens, termijn in await _escalatiekandidaten(sessie, klok):
            # NOODSTOP PER KLANT (ADR-036 OP-03, Gate 2 ronde 2 punt 1): escaleren is het wettelijke
            # vervolg van een herinnering, dus een deur. Het dossier van een stilgezette klant
            # blijft `herinnerd` en komt na het opheffen alsnog aan de beurt. Fail-closed: een
            # stand die niet te lezen is telt als stil.
            if await klant_staat_stil(tenant_id):
                overgeslagen += 1
                continue
            try:
                gedaan = await _escaleer(sessie, receivable_id, tenant_id, grens)
            except SQLAlchemyError:
                logger.error(
                    "debiteuren opvolgen: dossier %s niet verwerkt (databasefout)",
                    receivable_id,
                    exc_info=True,
                )
                await sessie.rollback()
                continue
            if gedaan:
                geescaleerd += 1
                await _log_escalatie(sessie, receivable_id, tenant_id)
                await _meld_escalatie(sessie, receivable_id, tenant_id, termijn)
    if geescaleerd:
        logger.info("debiteuren opvolgen: %d dossiers geescaleerd", geescaleerd)
    if overgeslagen:
        logger.warning("debiteuren opvolgen: %d dossiers overgeslagen (noodstop)", overgeslagen)


@workflow_actor(
    queue_name="default",
    max_retries=0,
    time_limit=300_000,
    actor_name="volg_debiteuren_op",
)
def volg_debiteuren_op() -> None:
    """Dramatiq-ingang: een keer per dag door de scheduler gestart.

    `max_retries=0`: de volgende dagrun pakt wat is blijven liggen; escaleren is idempotent
    omdat alleen `herinnerd` dossiers worden gekozen.
    """
    draai_in_eigen_loop(volg_debiteuren_op_async)
