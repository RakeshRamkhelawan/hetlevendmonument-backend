"""SupplierRepository en PayableRepository -- lezen en schrijven van leveranciers en inkoopfacturen, altijd binnen een tenant.

`tenant_id` is een verplichte parameter van elke methode en komt van de aanroeper (die hem uit de JWT-context haalt). De
invoerobjecten `NewSupplier` en `NewPayable` hebben bewust GEEN tenantveld: een verzoek of payload kan de tenant dus niet kiezen.

Elke query filtert zelf op `tenant_id`, naast de `do_orm_execute`-hook. Dubbel, en bewust: achtergrondtaken en tests draaien
zonder die hook, en dan is dit filter het enige. Daaronder staat Row Level Security (migratie `20261024_payables_rls.py`) en de
samengestelde sleutel van een factuur naar zijn leverancier.

Statusverloop (brief crediteuren dag 1): `ontvangen -> gecontroleerd -> goedgekeurd -> in_betaalbestand -> betaald`, plus
`afgewezen`. Dag 1 bouwt alleen de overgang naar `gecontroleerd`; de rest staat al in de tabel van toegestane overgangen, maar
`set_status` weigert die stappen tot ze er zijn (dag 3 en 4), met een Nederlandse tekst.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidatieFout
from src.core.models.payable_models import PAYABLE_STATUSES, Payable, Supplier

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewSupplier:
    """De velden van een nieuwe leverancier, zonder tenant."""

    name: str
    iban: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class NewPayable:
    """De velden van een nieuwe inkoopfactuur, zonder tenant. `amount_cents` is een geheel aantal centen."""

    supplier_id: int
    invoice_number: str
    amount_cents: int
    invoice_date: date
    due_date: date
    currency: str = "EUR"


#: Drie hoofdletters A-Z (ISO 4217-vorm). De database heeft een ruimere regel als vangnet (`ck_payables_currency_iso`).
_VALUTA = re.compile(r"[A-Z]{3}")
#: Vorm van een IBAN: landcode, twee controlecijfers, dan hoogstens dertig tekens. De controle-som staat in `_iban_klopt`.
_IBAN_VORM = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{1,30}")


#: De lengte van een IBAN per SEPA-land (ISO 13616-register). Bij een typefout klopt de controlesom in 1 van de 97 gevallen
#: toevallig toch; de lengte vangt dan alsnog de meeste fouten. Een land dat hier niet staat houdt alleen de controlesom: voor
#: het betaalbestand (dag 4) filtert de crediteurenkant toch op SEPA.
_IBAN_LENGTE: dict[str, int] = {
    "AD": 24, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24, "DE": 22, "DK": 18, "EE": 20,
    "ES": 24, "FI": 18, "FR": 27, "GB": 22, "GR": 27, "HR": 21, "HU": 28, "IE": 22, "IS": 26, "IT": 27,
    "LI": 21, "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MT": 31, "NL": 18, "NO": 15, "PL": 28, "PT": 25,
    "RO": 24, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "VA": 22,
}  # fmt: skip


def _iban_klopt(iban: str) -> bool:
    """ISO 13616: verplaats de eerste vier tekens naar achteren, letters worden 10-35, de rest moet 1 zijn modulo 97."""
    if not _IBAN_VORM.fullmatch(iban) or len(iban) < 15:
        return False
    lengte = _IBAN_LENGTE.get(iban[:2])
    if lengte is not None and len(iban) != lengte:
        return False
    herschikt = iban[4:] + iban[:4]
    getal = "".join(str(int(teken, 36)) for teken in herschikt)
    return int(getal) % 97 == 1


def _normaliseer_iban(iban: str | None) -> str | None:
    """Spaties eruit en hoofdletters; een leeg adres telt als geen IBAN. Ongeldig geeft een Nederlandse fout."""
    if iban is None or not iban.strip():
        return None
    schoon = re.sub(r"\s+", "", iban).upper()
    if not _iban_klopt(schoon):
        raise ValidatieFout(
            "Het IBAN-nummer is niet geldig. Controleer het nummer van de leverancier."
        )
    return schoon


def probeer_iban(iban: str | None) -> str | None:
    """Het IBAN zonder spaties en in hoofdletters, of `None` als het er geen is of het niet klopt (geen fout).

    Voor het zoeken en vergelijken van een GELEZEN IBAN: een onleesbaar nummer is dan "geen treffer", geen weigering.
    """
    try:
        return _normaliseer_iban(iban)
    except ValidatieFout:
        return None


def is_sepa_iban(iban: str | None) -> bool:
    """Is dit een geldig IBAN uit een land waarvan de lengte hierboven bekend is (de SEPA-zone)? Voor het betaalbestand.

    Een IBAN uit een land buiten de lijst (bijvoorbeeld de VS) klopt wel qua controlesom, maar kan niet via een SEPA-overschrijving.
    """
    schoon = probeer_iban(iban)
    return schoon is not None and schoon[:2] in _IBAN_LENGTE


def _controleer_bedrag(amount_cents: object) -> None:
    # bool is een int in Python; een True als bedrag is een fout in de aanroeper, geen ingevoerd bedrag.
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool):
        raise TypeError(
            "amount_cents moet een geheel aantal centen zijn (int), geen float, bool of tekst"
        )
    if amount_cents <= 0:
        raise ValidatieFout("Het bedrag moet groter zijn dan nul.")


def _controleer_valuta(currency: object) -> None:
    if not isinstance(currency, str) or not _VALUTA.fullmatch(currency):
        raise ValidatieFout("De valuta moet uit drie hoofdletters bestaan, bijvoorbeeld EUR.")


def _controleer_status(status: str) -> None:
    if status not in PAYABLE_STATUSES:
        raise ValidatieFout(f"Onbekende status: {status!r}.")


#: Toegestane statusovergangen over het hele verloop. Wat dag 1 mag zetten staat in `_NU_TOEGESTAAN`.
_OVERGANGEN: dict[str, frozenset[str]] = {
    "ontvangen": frozenset({"gecontroleerd", "afgewezen"}),
    "gecontroleerd": frozenset({"goedgekeurd", "afgewezen"}),
    "goedgekeurd": frozenset({"in_betaalbestand", "afgewezen"}),
    "in_betaalbestand": frozenset({"betaald"}),
    "betaald": frozenset(),
    "afgewezen": frozenset(),
}

#: De stappen die dit stadium van de bouw mag zetten. Goedkeuren is dag 3 (met een eigen recht en vier ogen), het
#: betaalbestand en afboeken zijn dag 4; afwijzen krijgt een eigen route met een reden.
_NU_TOEGESTAAN = frozenset({"gecontroleerd"})


def _controleer_overgang(van: str, naar: str) -> None:
    # Eerst wat er nog niet is: "kan niet van ontvangen naar goedgekeurd" zou suggereren dat het nooit kan. `ontvangen` is geen
    # latere stap maar de beginstand: daar hoort de gewone tekst "kan niet" bij.
    if naar != "ontvangen" and naar not in _NU_TOEGESTAAN:
        raise ValidatieFout(
            f"De status {naar!r} hoort bij een latere stap (goedkeuren, het betaalbestand, afboeken of afwijzen) "
            "en is nog niet beschikbaar."
        )
    if naar not in _OVERGANGEN.get(van, frozenset()):
        raise ValidatieFout(f"De status kan niet van {van!r} naar {naar!r} worden gezet.")


def _is_dubbel(fout: IntegrityError, indexnaam: str) -> bool:
    """Is dit de botsing op DE unieke index met deze naam? Elke andere IntegrityError (sleutel, CHECK) is een programmeerfout en
    wordt niet als "al vastgelegd" aan de klant voorgesteld (Gate 2). PostgreSQL noemt de index in de melding."""
    return indexnaam in str(fout.orig)


class IbanAlInGebruik(ValidatieFout):
    """Het IBAN hoort binnen deze tenant al bij een andere leverancier (een eigen soort, zodat de goedkeurder een vaste zin krijgt)."""


class SupplierRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, tenant_id: int, data: NewSupplier) -> Supplier:
        iban = _normaliseer_iban(data.iban)
        naam = data.name.strip()
        bestaand = (
            await self.db.execute(
                select(Supplier.id).where(
                    Supplier.tenant_id == tenant_id, func.lower(Supplier.name) == func.lower(naam)
                )
            )
        ).first()
        if bestaand is not None:
            raise ValidatieFout("Er bestaat al een leverancier met deze naam.")
        await self._controleer_iban_vrij(tenant_id, iban, behalve=None)
        rij = Supplier(tenant_id=tenant_id, name=naam, iban=iban, email=data.email)
        self.db.add(rij)
        try:
            # Een eigen savepoint: een botsing (twee gelijktijdige invoeren) laat de sessie bruikbaar achter.
            async with self.db.begin_nested():
                await self.db.flush()
        except IntegrityError as exc:
            if _is_dubbel(exc, "uq_suppliers_tenant_lower_name") or _is_dubbel(exc, "suppliers.tenant_id"):
                raise ValidatieFout("Er bestaat al een leverancier met deze naam.") from exc
            logger.error("leverancier vastleggen mislukte: %s: %s", type(exc).__name__, exc, exc_info=True)
            raise
        return rij

    async def get(self, tenant_id: int, supplier_id: int) -> Supplier | None:
        result = await self.db.execute(
            select(Supplier).where(Supplier.id == supplier_id, Supplier.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def find_match(
        self, tenant_id: int, *, naam: str | None, iban: str | None
    ) -> tuple[Supplier, str] | None:
        """Een bekende leverancier van DEZE tenant voor een gelezen factuur: eerst op IBAN, dan op naam.

        Geeft de rij en waarop hij gevonden is (`"iban"` of `"naam"`). De naam telt hoofdletterongevoelig, zoals de unieke index.
        Meerdere treffers op een IBAN: de oudste (laagste id), zodat het antwoord niet van de volgorde in de database afhangt.
        """
        schoon_iban = probeer_iban(iban)
        if schoon_iban is not None:
            op_iban = await self.db.execute(
                select(Supplier)
                .where(Supplier.tenant_id == tenant_id, Supplier.iban == schoon_iban)
                .order_by(Supplier.id)
                .limit(1)
            )
            rij = op_iban.scalar_one_or_none()
            if rij is not None:
                return rij, "iban"
        schoon_naam = (naam or "").strip()
        if schoon_naam:
            op_naam = await self.db.execute(
                select(Supplier).where(
                    Supplier.tenant_id == tenant_id, func.lower(Supplier.name) == func.lower(schoon_naam)
                )
            )
            rij = op_naam.scalar_one_or_none()
            if rij is not None:
                return rij, "naam"
        return None

    async def update_iban(self, tenant_id: int, supplier_id: int, iban: str) -> Supplier | None:
        """Zet het IBAN van een leverancier van DEZE tenant. Alleen voor een uitdrukkelijk goedgekeurde wijziging.

        Het IBAN van een bekende leverancier verandert nooit stil: de aanroeper is de crediteurenagent na een goedgekeurd ticket
        (`tool_broker/payables_registry.py`). Het nummer wordt gecontroleerd en genormaliseerd zoals bij `add`.
        """
        rij = await self.get(tenant_id, supplier_id)
        if rij is None:
            return None
        nieuw = _normaliseer_iban(iban)
        await self._controleer_iban_vrij(tenant_id, nieuw, behalve=supplier_id)
        rij.iban = nieuw
        await self.db.flush()
        return rij

    async def _controleer_iban_vrij(self, tenant_id: int, iban: str | None, *, behalve: int | None) -> None:
        """Een IBAN hoort bij een leverancier: weiger een IBAN dat binnen DEZE tenant al bij een andere leverancier hoort.

        Een controle in de applicatie en bewust geen unieke index (geen migratie; een index kan falen op bestaande dubbele rijen). Twee
        gelijktijdige aanvragen met hetzelfde nieuwe IBAN kunnen er dus allebei doorheen: het betaalbestand weigert die situatie zelf
        nog een keer (`payment_run_registry.maak_betaalbestand`). Een andere tenant telt niet mee.
        """
        if iban is None:
            return
        voorwaarden = [Supplier.tenant_id == tenant_id, Supplier.iban == iban]
        if behalve is not None:
            voorwaarden.append(Supplier.id != behalve)
        andere = (
            await self.db.execute(select(Supplier.name).where(*voorwaarden).order_by(Supplier.id).limit(1))
        ).scalar_one_or_none()
        if andere is not None:
            raise IbanAlInGebruik(
                f"Dit IBAN hoort al bij de leverancier {andere!r}. Een IBAN hoort bij een leverancier; "
                "controleer of dit dezelfde leverancier is."
            )

    async def list_for_tenant(
        self, tenant_id: int, *, limit: int = 50, offset: int = 0
    ) -> list[Supplier]:
        result = await self.db.execute(
            select(Supplier)
            .where(Supplier.tenant_id == tenant_id)
            .order_by(Supplier.name, Supplier.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def commit_and_refresh(self, rij: Supplier) -> None:
        """Leg de wijziging vast en lees de rij terug (servergezette velden zoals `created_at`).

        Hier en niet in de router: ADR-033 laat een routerbestand geen databasesessie kennen.
        """
        await self.db.commit()
        await self.db.refresh(rij)


class PayableRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, tenant_id: int, data: NewPayable, *, created_by: int | None) -> Payable:
        _controleer_bedrag(data.amount_cents)
        _controleer_valuta(data.currency)
        if data.due_date < data.invoice_date:
            raise ValidatieFout("De vervaldatum mag niet voor de factuurdatum liggen.")
        nummer = data.invoice_number.strip()
        # De leverancier moet van DEZE tenant zijn; de samengestelde sleutel in de database is het vangnet hieronder.
        leverancier = await SupplierRepository(self.db).get(tenant_id, data.supplier_id)
        if leverancier is None:
            raise ValidatieFout("Deze leverancier bestaat niet.")
        bestaand = (
            await self.db.execute(
                select(Payable.id).where(
                    Payable.tenant_id == tenant_id,
                    Payable.supplier_id == data.supplier_id,
                    func.lower(Payable.invoice_number) == func.lower(nummer),
                )
            )
        ).first()
        if bestaand is not None:
            raise ValidatieFout("Deze factuur van deze leverancier is al vastgelegd.")
        rij = Payable(
            tenant_id=tenant_id,
            supplier_id=data.supplier_id,
            invoice_number=nummer,
            amount_cents=data.amount_cents,
            currency=data.currency,
            invoice_date=data.invoice_date,
            due_date=data.due_date,
            status="ontvangen",
            created_by_user_id=created_by,
        )
        self.db.add(rij)
        try:
            async with self.db.begin_nested():
                await self.db.flush()
        except IntegrityError as exc:
            if _is_dubbel(exc, "uq_payables_tenant_supplier_lower_invoice") or _is_dubbel(exc, "payables.tenant_id"):
                raise ValidatieFout("Deze factuur van deze leverancier is al vastgelegd.") from exc
            logger.error("inkoopfactuur vastleggen mislukte: %s: %s", type(exc).__name__, exc, exc_info=True)
            raise
        return rij

    async def find_duplicate(
        self, tenant_id: int, supplier_id: int, invoice_number: str
    ) -> Payable | None:
        """De factuur van deze leverancier met dit nummer binnen DEZE tenant, hoofdletterongevoelig (zoals de unieke index)."""
        result = await self.db.execute(
            select(Payable).where(
                Payable.tenant_id == tenant_id,
                Payable.supplier_id == supplier_id,
                func.lower(Payable.invoice_number) == func.lower(invoice_number.strip()),
            )
        )
        return result.scalar_one_or_none()

    async def get(self, tenant_id: int, payable_id: int, *, lock: bool = False) -> Payable | None:
        vraag = (
            select(Payable)
            .where(Payable.id == payable_id, Payable.tenant_id == tenant_id)
            # Ververs een rij die de sessie al kent: na `set_status` moet de volgende lezer de nieuwe stand zien.
            .execution_options(populate_existing=True)
        )
        if lock:
            # Rijslot: twee gelijktijdige statuswijzigingen lazen anders allebei de oude stand en schreven allebei (Gate 2).
            # `of=Payable`: PostgreSQL staat FOR UPDATE niet toe op de nullable kant van de joined leverancier.
            vraag = vraag.with_for_update(of=Payable)
        result = await self.db.execute(vraag)
        return result.unique().scalar_one_or_none()

    async def list_for_tenant(
        self, tenant_id: int, *, limit: int = 50, offset: int = 0, status: str | None = None
    ) -> list[Payable]:
        if status is not None:
            _controleer_status(status)
        vraag = select(Payable).where(Payable.tenant_id == tenant_id)
        if status is not None:
            vraag = vraag.where(Payable.status == status)
        result = await self.db.execute(
            vraag.order_by(Payable.due_date, Payable.id).limit(limit).offset(offset)
        )
        return list(result.unique().scalars().all())

    async def set_status(
        self, tenant_id: int, payable_id: int, naar: str, *, door: int | None
    ) -> Payable | None:
        """Zet de status van een factuur van DEZE tenant. `None` als hij niet bestaat binnen de tenant.

        `door` is de gebruiker die de stap zet; bij `gecontroleerd` wordt hij met het tijdstip op de rij vastgelegd.
        """
        _controleer_status(naar)
        rij = await self.get(tenant_id, payable_id, lock=True)
        if rij is None:
            return None
        _controleer_overgang(rij.status, naar)
        rij.status = naar
        if naar == "gecontroleerd":
            rij.checked_by_user_id = door
            rij.checked_at = datetime.now(timezone.utc)
        await self.db.flush()
        return rij

    async def keur_goed_voor_betaling(
        self, tenant_id: int, payable_ids: list[int], *, door: int | None
    ) -> list[int]:
        """Zet facturen van DEZE tenant op `goedgekeurd`, maar alleen wat nog `ontvangen` of `gecontroleerd` is. Geeft de id's terug.

        Een atomaire UPDATE met de statusvoorwaarde in de WHERE (geen lezen-dan-schrijven): twee voorstellen met dezelfde factuur kunnen
        hem niet allebei goedkeuren. De aanroeper vergelijkt het aantal en draait terug als het kleiner is dan gevraagd. Dit is de
        enige weg naar `goedgekeurd`: de gewone statusroute weigert die stap.

        Let op, bewust: een `ontvangen` factuur gaat rechtstreeks naar `goedgekeurd` (de brief laat beide statussen toe) en `checked_by` en
        `checked_at` worden hier de goedkeurder en het goedkeurmoment, ook als iemand anders de factuur eerder `gecontroleerd` had. De
        auditregel `payment_run_approved` bewaart wie goedkeurde; `checked_at` is het ijkmoment voor "leverancier gewijzigd na goedkeuring".
        """
        if not payable_ids:
            return []
        nu = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(Payable)
            .where(
                Payable.tenant_id == tenant_id,
                Payable.id.in_(payable_ids),
                Payable.status.in_(("ontvangen", "gecontroleerd")),
            )
            .values(status="goedgekeurd", checked_by_user_id=door, checked_at=nu)
            .returning(Payable.id)
        )
        return sorted(int(rij_id) for rij_id in result.scalars().all())

    async def trek_goedkeuring_in(
        self, tenant_id: int, payable_ids: list[int], *, naar: str
    ) -> list[int]:
        """Haal facturen van DEZE tenant terug uit `goedgekeurd`, zolang ze in geen betaalbestand zitten. Geeft de id's terug.

        `naar` is `afgewezen` (een factuur die niet betaald moet worden) of `gecontroleerd` (de factuur komt vrij voor een nieuw
        voorstel). Een atomaire UPDATE met `status = 'goedgekeurd'` in de WHERE, net als `claim_voor_betaalbestand`: een factuur die
        intussen in een bestand is gekomen of al is ingetrokken wordt niet aangeraakt, en twee gelijktijdige aanroepen kunnen niet
        allebei slagen. De aanroeper vergelijkt het aantal met wat hij vroeg.
        """
        if naar not in ("afgewezen", "gecontroleerd"):
            raise ValueError(f"intrekken kan alleen naar afgewezen of gecontroleerd, niet naar {naar!r}")
        if not payable_ids:
            return []
        result = await self.db.execute(
            update(Payable)
            .where(
                Payable.tenant_id == tenant_id,
                Payable.id.in_(payable_ids),
                Payable.status == "goedgekeurd",
            )
            .values(status=naar)
            .returning(Payable.id)
        )
        return sorted(int(rij_id) for rij_id in result.scalars().all())

    async def claim_voor_betaalbestand(self, tenant_id: int) -> list[Payable]:
        """Zet ALLE `goedgekeurde` facturen van DEZE tenant op `in_betaalbestand` en geeft ze terug (met leverancier).

        Een atomaire UPDATE ... RETURNING: een factuur kan hierdoor in hooguit een bestand terechtkomen, ook als twee mensen tegelijk
        downloaden (de tweede krijgt een lege lijst). De aanroeper bouwt het bestand in dezelfde transactie en draait terug als dat
        mislukt.
        """
        result = await self.db.execute(
            update(Payable)
            .where(Payable.tenant_id == tenant_id, Payable.status == "goedgekeurd")
            .values(status="in_betaalbestand")
            .returning(Payable.id)
        )
        ids = [int(rij_id) for rij_id in result.scalars().all()]
        if not ids:
            return []
        rijen = await self.db.execute(
            select(Payable)
            .where(Payable.tenant_id == tenant_id, Payable.id.in_(ids))
            .order_by(Payable.due_date, Payable.id)
            .execution_options(populate_existing=True)
        )
        return list(rijen.unique().scalars().all())

    async def commit_and_refresh(self, rij: Payable) -> None:
        """Leg de wijziging vast en lees de rij terug (servergezette velden zoals `created_at`)."""
        await self.db.commit()
        await self.db.refresh(rij)
