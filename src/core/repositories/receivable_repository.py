"""ReceivableRepository -- lezen en schrijven van debiteuren, altijd binnen een tenant.

`tenant_id` is een verplichte parameter van elke methode en komt van de aanroeper (die hem
uit de JWT-context haalt). De invoer `NewReceivable` heeft bewust GEEN tenantveld: een
verzoek of payload kan de tenant dus niet kiezen.

Elke query filtert zelf op `tenant_id`, naast de `do_orm_execute`-hook. Dubbel, en bewust:
achtergrondtaken en tests draaien zonder die hook, en dan is dit filter het enige.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidatieFout
from src.core.models.outgoing_message_models import (
    FOUTREDEN_GEANNULEERD_BETAALD,
    MAX_POGINGEN,
    OutgoingMessage,
)
from src.core.models.receivable_models import (
    RECEIVABLE_SOURCES,
    RECEIVABLE_STATUSES,
    Receivable,
)


@dataclass(frozen=True)
class NewReceivable:
    """De velden van een nieuwe debiteur, zonder tenant."""

    customer_name: str
    customer_email: str
    invoice_number: str
    amount: Decimal
    due_date: date
    currency: str = "EUR"
    status: str = "open"
    source: str = "handmatig"
    external_id: str | None = None


@dataclass(frozen=True)
class ReceivableChanges:
    """Een wijziging van een bestaande debiteur: alleen de velden die niet `None` zijn.

    Bewust zonder `source` en `external_id`: de herkomst van een rij verandert niet door hem met
    de hand te bewerken, en de unieke sleutel van een import hangt eraan. Geen tenantveld.
    """

    customer_name: str | None = None
    customer_email: str | None = None
    invoice_number: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    due_date: date | None = None
    status: str | None = None
    #: Waarom een betaling wordt teruggedraaid; alleen daar verplicht, nooit opgeslagen op de rij.
    reden: str | None = None


#: Drie hoofdletters A-Z (ISO 4217-vorm). De database heeft een ruimere regel als vangnet
#: (`ck_receivables_currency_iso`); de volle vorm wordt hier getoetst.
_VALUTA = re.compile(r"[A-Z]{3}")


def _controleer_bedrag(amount: object) -> None:
    if not isinstance(amount, Decimal):
        raise TypeError("amount moet een Decimal zijn, geen float of int")
    if not amount.is_finite() or amount < 0:
        raise ValidatieFout("Het bedrag mag niet negatief zijn.")


def _controleer_valuta(currency: object) -> None:
    if not isinstance(currency, str) or not _VALUTA.fullmatch(currency):
        raise ValidatieFout("De valuta moet uit drie hoofdletters bestaan, bijvoorbeeld EUR.")


def _controleer_status(status: str) -> None:
    if status not in RECEIVABLE_STATUSES:
        raise ValidatieFout(f"Onbekende status: {status!r}.")


#: Toegestane statusovergangen. `betaald` is bereikbaar vanuit elke status; terug van `betaald`
#: kan naar elke andere status, maar alleen met een reden (zie `_controleer_overgang`).
_OVERGANGEN: dict[str, frozenset[str]] = {
    "open": frozenset({"herinnerd", "betaald"}),
    "herinnerd": frozenset({"geescaleerd", "betaald"}),
    "geescaleerd": frozenset({"betaald"}),
    "betaald": frozenset({"open", "herinnerd", "geescaleerd"}),
}


#: Statussen die geen gebruiker en geen workflow zet. `herinnerd` is een feit: de verzendlus
#: (`debiteuren_tasks._verwerk`) zet hem pas als de brief verzonden is, en de 14-dagenklok van
#: de opvolging telt vanaf dat moment. `geescaleerd` zet de opvolging zelf.
_ALLEEN_DOOR_DE_KETEN = frozenset({"herinnerd", "geescaleerd"})


def _controleer_overgang(van: str, naar: str, reden: str | None) -> None:
    if van == naar:
        return
    if naar not in _OVERGANGEN.get(van, frozenset()):
        raise ValidatieFout(f"De status kan niet van {van!r} naar {naar!r} worden gezet.")
    if van == "betaald" and not (reden and reden.strip()):
        raise ValidatieFout("Een betaalde factuur terugzetten vraagt een reden.")


def _controleer(data: NewReceivable) -> None:
    """Weiger onbruikbare invoer luid, in plaats van hem stil aan te passen."""
    _controleer_bedrag(data.amount)
    _controleer_valuta(data.currency)
    _controleer_status(data.status)
    if data.source not in RECEIVABLE_SOURCES:
        raise ValidatieFout(f"Onbekende bron: {data.source!r}.")


def _controleer_wijziging(changes: ReceivableChanges) -> None:
    if changes.amount is not None:
        _controleer_bedrag(changes.amount)
    if changes.currency is not None:
        _controleer_valuta(changes.currency)
    if changes.status is not None:
        _controleer_status(changes.status)


class ReceivableRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, tenant_id: int, data: NewReceivable) -> Receivable:
        _controleer(data)
        rij = Receivable(
            tenant_id=tenant_id,
            customer_name=data.customer_name,
            customer_email=data.customer_email,
            invoice_number=data.invoice_number,
            amount=data.amount,
            currency=data.currency,
            due_date=data.due_date,
            status=data.status,
            source=data.source,
            external_id=data.external_id,
        )
        self.db.add(rij)
        await self.db.flush()
        return rij

    async def get(self, tenant_id: int, receivable_id: int) -> Receivable | None:
        result = await self.db.execute(
            select(Receivable).where(
                Receivable.id == receivable_id, Receivable.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_tenant(
        self, tenant_id: int, *, limit: int = 50, offset: int = 0
    ) -> list[Receivable]:
        result = await self.db.execute(
            select(Receivable)
            .where(Receivable.tenant_id == tenant_id)
            .order_by(Receivable.due_date, Receivable.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_all_for_matching(self, tenant_id: int, *, limit: int) -> list[Receivable]:
        """Alle vorderingen van DEZE tenant om een bankafschrift tegen te leggen (hoogstens `limit`, op id)."""
        result = await self.db.execute(
            select(Receivable)
            .where(Receivable.tenant_id == tenant_id)
            .order_by(Receivable.id)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_paid_via_statement(
        self, tenant_id: int, receivable_id: int, betaald_op: date | None
    ) -> Receivable | None:
        """Vink een vordering af op grond van een bankafschrift; geen commit.

        `None` als de vordering niet van deze tenant is of al betaald is: een tweede keer afvinken kan dus niet.
        """
        # Met rijslot: twee gelijktijdige uploads (of een upload en een wijziging met de hand) lezen anders allebei
        # "open" en vinken allebei af, met een dubbele auditregel en een overschreven datum (Gate 2).
        rij = (
            await self.db.execute(
                select(Receivable)
                .where(Receivable.id == receivable_id, Receivable.tenant_id == tenant_id)
                .with_for_update()
                # Ververs een rij die de sessie al kent: zonder dit blijft de OUDE status staan en doet het slot niets.
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if rij is None or rij.status == "betaald":
            return None
        bijgewerkt = await self.update(tenant_id, receivable_id, ReceivableChanges(status="betaald"))
        if bijgewerkt is not None and betaald_op is not None:
            bijgewerkt.betaald_op = datetime(
                betaald_op.year, betaald_op.month, betaald_op.day, tzinfo=timezone.utc
            )
            await self.db.flush()
        return bijgewerkt

    async def update(
        self, tenant_id: int, receivable_id: int, changes: ReceivableChanges
    ) -> Receivable | None:
        """Wijzig een debiteur van DEZE tenant. `None` als hij niet bestaat binnen de tenant."""
        _controleer_wijziging(changes)
        rij = await self.get(tenant_id, receivable_id)
        if rij is None:
            return None
        oude_status = rij.status
        if changes.status in _ALLEEN_DOOR_DE_KETEN and changes.status != oude_status:
            raise ValidatieFout(
                f"De status {changes.status!r} zet alleen de keten zelf: 'herinnerd' de "
                "verzendlus na een verzonden brief, 'geescaleerd' de opvolging."
            )
        if changes.status is not None:
            _controleer_overgang(oude_status, changes.status, changes.reden)
        for veld in fields(changes):
            waarde = getattr(changes, veld.name)
            if waarde is not None and veld.name != "reden":
                setattr(rij, veld.name, waarde)
        if changes.status is not None and changes.status != oude_status:
            if changes.status == "betaald":
                rij.betaald_op = datetime.now(timezone.utc)
                # In dezelfde transactie: een brief die nog niet is verstuurd mag niet meer weg (B1, 2026-10-20).
                await self._annuleer_onverstuurde_berichten(tenant_id, receivable_id)
            elif oude_status == "betaald":
                rij.betaald_op = None
        await self.db.flush()
        return rij

    async def _annuleer_onverstuurde_berichten(self, tenant_id: int, receivable_id: int) -> None:
        """Annuleer de berichten van deze vordering die nog niet zijn verstuurd (klaar, of mislukt met pogingen over).

        Een geannuleerd bericht is `mislukt` met `pogingen = MAX_POGINGEN` en een foutreden "Geannuleerd: ...": de
        CHECK op `outgoing_messages.status` kent geen eigen status. Een al verzonden bericht blijft zoals het is.
        """
        await self.db.execute(
            update(OutgoingMessage)
            .where(
                OutgoingMessage.tenant_id == tenant_id,
                OutgoingMessage.receivable_id == receivable_id,
                or_(
                    OutgoingMessage.status == "klaar",
                    and_(
                        OutgoingMessage.status == "mislukt", OutgoingMessage.pogingen < MAX_POGINGEN
                    ),
                ),
            )
            .values(
                status="mislukt", pogingen=MAX_POGINGEN, foutreden=FOUTREDEN_GEANNULEERD_BETAALD
            )
        )

    async def commit_and_refresh(self, rij: Receivable) -> None:
        """Leg de wijziging vast en lees de rij terug (servergezette velden zoals `created_at`).

        Hier en niet in de router: ADR-033 laat een routerbestand geen databasesessie kennen.
        """
        await self.db.commit()
        await self.db.refresh(rij)
