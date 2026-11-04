"""Een inkoopfactuur inlezen met de bonlezer: voorstel en bevestiging door een mens (crediteuren dag 2, Keten F).

De bonlezer (upload, veiligheidscontrole, lezen zonder netwerk, eigen worker) is hergebruikt zoals hij is; dit bestand doet alleen wat
bij een INKOOPFACTUUR hoort en bij een bon niet:

- `voorstel`: de gelezen velden, plus welke bekende leverancier erbij hoort en of het IBAN op de factuur afwijkt van dat van de
  leverancier. Er wordt niets vastgelegd.
- `bevestig`: pas nadat een medewerker de (eventueel aangepaste) velden bevestigt ontstaat er een inkoopfactuur met status
  `ontvangen`. De velden komen uit het verzoek van de medewerker, NIET uit het leesresultaat: het resultaat van een worker die een
  vijandig bestand las is een voorstel, geen waarheid.

Een afwijkend IBAN bij een BEKENDE leverancier is een bekende fraudevorm (een valse factuur met een ander rekeningnummer). Het wordt
daarom nooit stil overgenomen: de bevestiging wordt geweigerd tot de medewerker het afwijkende nummer uitdrukkelijk bevestigt
(`iban_afwijking_bevestigd`), en ook dan blijft het IBAN van de leverancier zoals het was. Het IBAN van een factuur wordt niet op de
factuur bewaard; een betaling (dag 4) gebruikt het IBAN van de leverancier.

De tenant komt van de aanroeper (JWT), nooit uit het bestand of het verzoek. Het bestand van een andere tenant bestaat hier niet.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.als.bonlezer.factuur import FactuurKoppeling
from src.core.als.bonlezer.upload import BonDienst, BonNietGevonden
from src.core.exceptions import ValidatieFout
from src.core.repositories.payable_repository import (
    NewPayable,
    NewSupplier,
    PayableRepository,
    SupplierRepository,
    probeer_iban,
)

if TYPE_CHECKING:
    # Alleen voor de annotaties: een type is geen afhankelijkheid tijdens het draaien (en telt dus niet mee in de koppeling).
    from src.core.models.payable_models import Payable, Supplier

logger = logging.getLogger(__name__)

_NOG_NIET_GELEZEN = (
    "Deze factuur is nog niet gelezen. Wacht tot het lezen klaar is en probeer het dan opnieuw."
)
_NIET_GELEZEN = "Deze factuur kon niet worden gelezen. Voer de factuur met de hand in."
_AL_VASTGELEGD = "Deze factuur is al vastgelegd."
_IBAN_WIJKT_AF = (
    "Het IBAN op de factuur wijkt af van het IBAN van deze leverancier. Controleer dit eerst bij de leverancier: "
    "een ander rekeningnummer op een factuur is een bekende vorm van fraude. Bevestig alleen als u zeker weet dat het klopt."
)


class InlezenFout(Exception):
    """Een weigering met een tekst voor de medewerker; `status_code` is de HTTP-code."""

    def __init__(self, status_code: int, boodschap: str) -> None:
        super().__init__(boodschap)
        self.status_code = status_code
        self.boodschap = boodschap


@dataclass(frozen=True)
class Bevestiging:
    """Wat de medewerker bevestigt. Precies een van `supplier_id` en `nieuwe_leverancier` is gezet (toetst het schema)."""

    invoice_number: str
    amount_cents: int
    currency: str
    invoice_date: date
    due_date: date
    supplier_id: int | None = None
    nieuwe_leverancier: NewSupplier | None = None
    iban: str | None = None
    iban_afwijking_bevestigd: bool = False
    #: Aanpassen: het ticket van de agent dat hiermee sluit, en waarom de medewerker de factuur zelf vastlegt.
    ticket_ref: str = ""
    reden: str = ""


@dataclass(frozen=True)
class Vastgelegd:
    payable: Payable
    leverancier_nieuw: bool
    iban_afwijking_bevestigd: bool


class InkoopfactuurInlezen:
    def __init__(self, db: AsyncSession, dienst: BonDienst) -> None:
        self.db = db  # voor de auditregel van de aanroeper, zoals `repo.db`
        self._dienst = dienst
        # Dezelfde map als de dienst: de koppeling en de upload horen bij elkaar.
        self._koppeling = FactuurKoppeling(dienst.root)
        self._leveranciers = SupplierRepository(db)
        self._facturen = PayableRepository(db)

    async def voorstel(self, tenant_id: int, bestand_id: str) -> dict[str, object]:
        """De stand van het lezen, en bij `gelezen` ook het voorstel voor de leverancier. Legt niets vast."""
        data = await self._status(tenant_id, bestand_id)
        stand = await asyncio.to_thread(self._koppeling.lees, tenant_id, bestand_id)
        # Wat de agent ermee deed, voor het scherm: alleen de stand en verwijzingen, geen bedragen of IBAN's.
        data["verwerking"] = (
            {k: stand[k] for k in ("uitkomst", "ticket_ref", "payable_id", "reden") if k in stand}
            if stand
            else None
        )
        verwerking = data["verwerking"]
        if isinstance(verwerking, dict) and verwerking.get("payable_id") is None:
            # Een voorgelegde factuur: heeft de goedkeurder intussen besloten? Dan zegt de stand dat (afgekeurd of verlopen).
            besluit = await self._besluit_van_het_ticket(tenant_id, verwerking.get("ticket_ref"))
            if besluit is not None:
                verwerking["uitkomst"] = besluit
        if data.get("status") != "gelezen":
            return data
        velden = data.get("velden")
        gelezen = velden if isinstance(velden, dict) else {}
        data["voorstel"] = await self._leveranciersvoorstel(tenant_id, gelezen)
        return data

    async def bevestig(
        self, tenant_id: int, bestand_id: str, invoer: Bevestiging, *, user_id: int
    ) -> Vastgelegd:
        """Leg de inkoopfactuur vast die de medewerker bevestigt. Een upload wordt hooguit een keer een factuur."""
        data = await self._status(tenant_id, bestand_id)
        status = data.get("status")
        if status == "wachten":
            raise InlezenFout(409, _NOG_NIET_GELEZEN)
        if status != "gelezen":
            raise InlezenFout(409, _NIET_GELEZEN)
        # AANPASSEN: de upload is al geclaimd door de agent (voor DIT ticket); er wordt niet opnieuw beslag gelegd.
        await self._controleer_ticket(tenant_id, bestand_id, invoer.ticket_ref)
        try:
            vastgelegd = await self._leg_vast(tenant_id, invoer, user_id=user_id)
        except BaseException:
            # Een geweigerde of mislukte aanpassing laat het ticket open om te corrigeren; de sessie draait terug.
            await self.db.rollback()
            raise
        await asyncio.to_thread(
            self._koppeling.leg_vast, tenant_id, bestand_id, vastgelegd.payable.id, door=user_id
        )
        return vastgelegd

    # -- intern -------------------------------------------------------------------------------------

    async def _besluit_van_het_ticket(self, tenant_id: int, ticket_ref: object) -> str | None:
        """`afgewezen` of `verlopen` als het ticket van de agent zo is afgesloten; anders `None` (nog open of uitgevoerd)."""
        if not isinstance(ticket_ref, str):
            return None
        import importlib

        repo = importlib.import_module("src.core.tool_broker.hitl_repository").HITLTicketRepository
        ticket = await repo(self.db).get(ticket_ref, tenant_id)
        if ticket is None:
            return None
        return {"rejected": "afgewezen", "expired": "verlopen"}.get(str(ticket.status))

    async def ticket(self, tenant_id: int, ticket_ref: str) -> object:
        """Het ticket van DEZE tenant (voor de zelfgoedkeuringstoets van de aanroeper); 404 als het er niet is."""
        import importlib

        repo = importlib.import_module("src.core.tool_broker.hitl_repository").HITLTicketRepository
        ticket = await repo(self.db).get(ticket_ref, tenant_id)
        if ticket is None:
            raise InlezenFout(404, "Dit ticket bestaat niet.")
        return ticket

    async def _controleer_ticket(self, tenant_id: int, bestand_id: str, ticket_ref: str) -> None:
        """Hoort dit OPENSTAANDE ticket van de crediteurenagent bij deze upload? Anders 404 of 409."""
        import importlib

        repo = importlib.import_module("src.core.tool_broker.hitl_repository").HITLTicketRepository
        ticket = await repo(self.db).get(ticket_ref, tenant_id)
        if ticket is None:
            raise InlezenFout(404, "Dit ticket bestaat niet.")
        if ticket.tool_name != "propose_supplier_invoice" or ticket.status != "pending":
            raise InlezenFout(409, "Dit ticket is al afgehandeld of hoort niet bij een inkoopfactuur.")
        stand = await asyncio.to_thread(self._koppeling.lees, tenant_id, bestand_id)
        if not stand or stand.get("ticket_ref") != ticket_ref or stand.get("payable_id") is not None:
            raise InlezenFout(409, _AL_VASTGELEGD)

    async def _sluit_ticket(
        self, tenant_id: int, invoer: Bevestiging, payable_id: int, *, user_id: int
    ) -> None:
        """Sluit het ticket als afgewezen met de reden en een verwijzing naar de factuur (in dezelfde transactie)."""
        import importlib

        repo = importlib.import_module("src.core.tool_broker.hitl_repository").HITLTicketRepository
        notitie = (
            f"Afgewezen, handmatig vastgelegd als inkoopfactuur {payable_id}: {invoer.reden}"
        )[:1000]
        if not await repo(self.db).reject(invoer.ticket_ref, tenant_id, user_id, note=notitie):
            raise InlezenFout(409, "Dit ticket is al afgehandeld.")

    async def _status(self, tenant_id: int, bestand_id: str) -> dict[str, object]:
        # Een bon van de bonnenpagina is geen inkoopfactuur; die bestaat hier niet, ook niet voor wie het nummer kent.
        if await asyncio.to_thread(self._dienst.soort, tenant_id, bestand_id) != "factuur":
            raise InlezenFout(404, "Deze factuur bestaat niet.")
        try:
            return dict(await asyncio.to_thread(self._dienst.status, tenant_id, bestand_id))
        except BonNietGevonden as fout:
            raise InlezenFout(404, "Deze factuur bestaat niet.") from fout

    async def _leveranciersvoorstel(
        self, tenant_id: int, velden: dict[object, object]
    ) -> dict[str, object]:
        naam = velden.get("leverancier")
        iban = velden.get("iban")
        gelezen_iban = iban if isinstance(iban, str) else None
        gevonden = await self._leveranciers.find_match(
            tenant_id, naam=naam if isinstance(naam, str) else None, iban=gelezen_iban
        )
        if gevonden is None:
            return {
                "leverancier_id": None,
                "leverancier_naam": None,
                "gevonden_op": None,
                "bekend_iban": None,
                "iban_wijkt_af": False,
            }
        leverancier, gevonden_op = gevonden
        return {
            "leverancier_id": leverancier.id,
            "leverancier_naam": leverancier.name,
            "gevonden_op": gevonden_op,
            "bekend_iban": leverancier.iban,
            "iban_wijkt_af": _wijkt_af(leverancier.iban, gelezen_iban),
        }

    async def _leg_vast(self, tenant_id: int, invoer: Bevestiging, *, user_id: int) -> Vastgelegd:
        if invoer.nieuwe_leverancier is not None:
            leverancier = await self._leveranciers.add(tenant_id, invoer.nieuwe_leverancier)
        else:
            leverancier = await self._bekende_leverancier(tenant_id, invoer)
        nieuw = invoer.nieuwe_leverancier is not None
        rij = await self._facturen.add(
            tenant_id,
            NewPayable(
                supplier_id=leverancier.id,
                invoice_number=invoer.invoice_number,
                amount_cents=invoer.amount_cents,
                currency=invoer.currency,
                invoice_date=invoer.invoice_date,
                due_date=invoer.due_date,
            ),
            created_by=user_id,
        )
        await self._sluit_ticket(tenant_id, invoer, int(rij.id), user_id=user_id)
        await self._facturen.commit_and_refresh(rij)
        return Vastgelegd(
            payable=rij,
            leverancier_nieuw=nieuw,
            iban_afwijking_bevestigd=invoer.iban_afwijking_bevestigd and not nieuw,
        )

    async def _bekende_leverancier(self, tenant_id: int, invoer: Bevestiging) -> Supplier:
        leverancier = (
            await self._leveranciers.get(tenant_id, invoer.supplier_id)
            if invoer.supplier_id
            else None
        )
        if leverancier is None:
            raise ValidatieFout("Deze leverancier bestaat niet.")
        if invoer.iban is not None and invoer.iban.strip():
            gelezen = probeer_iban(invoer.iban)
            if gelezen is None:
                raise ValidatieFout(
                    "Het IBAN-nummer op de factuur is niet geldig. Controleer het nummer."
                )
            if _wijkt_af(leverancier.iban, gelezen) and not invoer.iban_afwijking_bevestigd:
                raise ValidatieFout(_IBAN_WIJKT_AF)
        return leverancier


def _wijkt_af(bekend: str | None, op_factuur: str | None) -> bool:
    """Wijkt het IBAN op de factuur af van het bekende IBAN? Zonder een van beide is er niets om mee te vergelijken."""
    gelezen = probeer_iban(op_factuur)
    return bekend is not None and gelezen is not None and bekend != gelezen
