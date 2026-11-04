"""Betaalrun voor de crediteurenagent: `propose_payment_run` en het betaalbestand (crediteuren dag 3, Keten F).

Gemodelleerd naar `payables_registry.py`: een tenant-gescoped brug tussen een ToolBroker-payload en de database. De tenant komt als los
argument van de broker (uit de executiecontext), nooit uit de payload.

**De keten, in drie stappen met drie verschillende handen**

1. De AGENT stelt voor (`selecteer` is het LEESpad; de tool `propose_payment_run` is HIGH): een ticket met de lijst facturen, het
   totaal en per regel het waarom. Alleen facturen met status `ontvangen` of `gecontroleerd`, in euro, van een bekende leverancier met een
   geldig SEPA-IBAN, die binnen `HORIZON_DAGEN` vervallen of al te laat zijn, en die niet al in een ander openstaand voorstel staan.
2. Een MENS keurt goed of wijst af met reden. Na goedkeuren komt de tool hier aan (`_voer_uit`): alle facturen van het voorstel gaan
   atomair naar `goedgekeurd`, of geen enkele. Boven het drempelbedrag (`Tenant.settings`: een factuur OF het totaal) geldt vier ogen: wie het voorstel
   liet maken, mag het niet zelf goedkeuren (`vier_ogen_vereist` in het ticket; de toets staat in de HITL-route).
3. Een MENS met het goedkeurrecht haalt het betaalbestand op (`maak_betaalbestand`): ALLE goedgekeurde facturen van de tenant gaan
   atomair naar `in_betaalbestand` en in een pain.001-bestand dat nergens heen gaat.

**Waarom het bestand eenmalig is (gemeten 2026-10-25).** `HITLTicketRepository.approve` vervangt de payload door een digest van de
parameters; na goedkeuren staan de factuurregels dus nergens meer. Zonder migratie (de brief verbiedt die zonder STOP) is er geen
plek om bij te houden welke facturen bij welk bestand horen. Een bestand opnieuw maken kan daarom niet: wie het kwijtraakt, vraagt de
regie om een ontwerpbesluit (opslag van het bestand). Dat is bewust de veilige kant: een tweede, identiek bestand is een dubbele betaling.

**Het IBAN blijft gebonden.** In het ticket staat het IBAN gemaskeerd (de inhoudswachter laat een geldig IBAN in een parameter niet door)
plus een digest van het hele nummer. Bij goedkeuren moet het IBAN van de leverancier nog dezelfde digest geven; bij het bestand gaat een
factuur waarvan de leverancier is gewijzigd na de goedkeuring (`updated_at` tegen `checked_at`) niet mee en keert terug naar `gecontroleerd`.

Een tool geeft geen persoonsgegevens terug: alleen `success` en aantallen.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import secrets
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, cast, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidatieFout
from src.core.models.payable_models import Payable
from src.core.repositories.payable_repository import PayableRepository, is_sepa_iban, probeer_iban
from src.core.services.sepa_betaalbestand import BetaalRegel, Betaalopdracht, maak_pain001
from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.models import HITLTicket
from src.core.tool_broker.payables_registry import _default_session_factory, maskeer_iban

TOOL_NAME = "propose_payment_run"

#: Sleutel in `Tenant.settings`: het bedrag (in centen) waarboven een betaling vier ogen vraagt, per factuur en voor het totaal van een voorstel.
SETTINGS_DREMPEL_KEY = "crediteur_betaal_drempel_cents"
#: Keuze regie 2026-10-24: 2.500 EUR, per klant aan te passen door de beheerder.
DREMPEL_STANDAARD_CENTS = 250_000
#: Een factuur die binnen zoveel dagen vervalt (of al te laat is) komt in een voorstel.
HORIZON_DAGEN = 7
#: Meer regels maken een ticket onleesbaar voor de goedkeurder; de rest komt in een volgend voorstel.
MAX_REGELS = 100

#: De sleutel in de payload van een GOEDGEKEURD voorstel met de id's van zijn facturen (de eigen binding van de run; zie `_voer_uit`).
RUN_FACTUREN_SLEUTEL = "_betaalrun_facturen"
#: Gezet bij het intrekken van een voorstel (in plaats van `RUN_FACTUREN_SLEUTEL`): een tweede intrekking op dezelfde ticketverwijzing mag de
#: facturen van een NIEUWER voorstel niet vrijgeven.
RUN_INGETROKKEN_SLEUTEL = "_betaalrun_ingetrokken"

_VELDEN = frozenset({"regels", "totaal_cents", "drempel_cents", "vier_ogen_vereist", "waarom"})
_REGEL_VELDEN = (
    "payable_id",
    "supplier_id",
    "supplier_name",
    "invoice_number",
    "amount_cents",
    "due_date",
    "iban",
    "iban_digest",
    "waarom",
)
_TE_BETALEN = ("ontvangen", "gecontroleerd")
#: Een goedgekeurd ticket is hooguit even "open" (de uitvoering volgt direct); daarna is het `consumed`. Blijft hij `approved` staan na een
#: gefaalde uitvoering, dan houdt hij zijn facturen niet voor altijd vast.
_APPROVED_VENSTER = timedelta(minutes=15)


def drempel_uit_settings(settings: object) -> int:
    """Het drempelbedrag in centen (per factuur en voor het totaal van een voorstel), uit `Tenant.settings`.

    Geen instelling: de standaard. Een instelling die geen positief geheel getal is, valt dicht naar 1 cent (elke betaling vraagt dan
    vier ogen): iemand heeft iets ingesteld dat niet te lezen is, en dan moet de regel strenger worden en niet losser.
    """
    if not isinstance(settings, dict) or SETTINGS_DREMPEL_KEY not in settings:
        return DREMPEL_STANDAARD_CENTS
    waarde = settings[SETTINGS_DREMPEL_KEY]
    if isinstance(waarde, int) and not isinstance(waarde, bool) and waarde > 0:
        return waarde
    return 1


def _schoon(tekst: str) -> str:
    """Door een mens geschreven tekst voor het auditlog: herkende persoonsgegevens gemaskeerd (zelfde opschoning als `redact_free_text`)."""
    enforcer = importlib.import_module("src.core.governance.gdpr_enforcer").GDPREnforcer()
    return str(enforcer.redact_pii(tekst)[0])


def iban_digest(tenant_id: int, iban: str) -> str:
    """Een vingerafdruk van het volledige IBAN, voor in het ticket waar het IBAN zelf niet in mag."""
    return hashlib.sha256(f"{tenant_id}:{iban}".encode("ascii")).hexdigest()[:24]


def _dagen_tekst(dagen: int) -> str:
    if dagen < 0:
        aantal = -dagen
        return f"{aantal} dag te laat" if aantal == 1 else f"{aantal} dagen te laat"
    if dagen == 0:
        return "vervalt vandaag"
    return "vervalt over 1 dag" if dagen == 1 else f"vervalt over {dagen} dagen"


def _euro(cents: int) -> str:
    euro, rest = divmod(cents, 100)
    hele = f"{euro:,}".replace(",", ".")
    return f"EUR {hele},{rest:02d}"


class BetaalrunToolRegistry:
    """Selecteert een betaalvoorstel, voert het uit na goedkeuren en maakt het betaalbestand, altijd binnen EEN tenant."""

    _TOOL_NAMES = frozenset({TOOL_NAME})

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
    ) -> None:
        self._session_factory = session_factory or _default_session_factory

    @classmethod
    def known_tool_names(cls) -> set[str]:
        """De toolnamen die deze registry afhandelt."""
        return set(cls._TOOL_NAMES)

    @asynccontextmanager
    async def _tenant_sessie(self, tenant_id: int) -> AsyncGenerator[AsyncSession, None]:
        """Een sessie met de tenant-ContextVar gezet, en daarna hersteld (RLS leest `app.current_tenant`)."""
        from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id

        vorige = get_tenant_id()
        set_tenant_id(tenant_id)
        try:
            async with self._session_factory() as session:
                yield session
        finally:
            set_tenant_id(vorige)

    @staticmethod
    def _controleer_tenant(tenant_id: object, tool_name: str = "payment_run") -> None:
        if not isinstance(tenant_id, int) or isinstance(tenant_id, bool) or tenant_id <= 0:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail="tenant_id must be a positive integer from the execution context",
            )

    # -- het voorstel (LEESpad) ---------------------------------------------------------------------

    async def selecteer(self, tenant_id: int, *, vandaag: date | None = None) -> dict[str, object]:
        """Welke facturen stelt de agent nu voor? Legt niets vast.

        Geeft `regels` (leeg als er niets te betalen is), `overgeslagen` (facturen die wel aan de beurt zijn maar niet kunnen, met
        reden), `totaal_cents`, `drempel_cents`, `vier_ogen_vereist` en `waarom`. De regels zijn precies wat in het ticket komt.
        """
        self._controleer_tenant(tenant_id)
        vandaag = vandaag or datetime.now(timezone.utc).date()
        async with self._tenant_sessie(tenant_id) as session:
            drempel = drempel_uit_settings(await self._tenant_settings(session, tenant_id))
            al_voorgesteld = await self._al_voorgesteld(session, tenant_id)
            eerder_verlopen = await self._laatste_voorstel_verlopen(session, tenant_id)
            vraag = (
                select(Payable)
                .where(
                    Payable.tenant_id == tenant_id,
                    Payable.status.in_(_TE_BETALEN),
                    Payable.currency == "EUR",
                    Payable.due_date <= vandaag + timedelta(days=HORIZON_DAGEN),
                )
                .order_by(Payable.due_date, Payable.id)
            )
            rijen = list((await session.execute(vraag)).unique().scalars().all())
        regels: list[dict[str, object]] = []
        overgeslagen: list[dict[str, object]] = []
        for rij in rijen:
            if rij.id in al_voorgesteld:
                continue
            leverancier = rij.supplier
            iban = probeer_iban(leverancier.iban)
            if iban is None or not is_sepa_iban(iban):
                overgeslagen.append(
                    {
                        "invoice_number": rij.invoice_number,
                        "reden": "de leverancier heeft geen geldig SEPA-IBAN",
                    }
                )
                continue
            if len(regels) >= MAX_REGELS:
                break
            regels.append(
                {
                    "payable_id": int(rij.id),
                    "supplier_id": int(rij.supplier_id),
                    "supplier_name": leverancier.name,
                    "invoice_number": rij.invoice_number,
                    "amount_cents": int(rij.amount_cents),
                    "due_date": rij.due_date.isoformat(),
                    "iban": maskeer_iban(iban),
                    "iban_digest": iban_digest(tenant_id, iban),
                    "waarom": _dagen_tekst((rij.due_date - vandaag).days),
                }
            )
        bedragen = [int(str(r["amount_cents"])) for r in regels]
        totaal = sum(bedragen)
        # Vier ogen als een factuur OF het totaal van het voorstel boven het drempelbedrag komt (besluit regie 2026-10-26: anders is
        # honderd keer net onder de drempel een voorstel van een kwart miljoen dat een persoon alleen goedkeurt).
        vier_ogen = any(bedrag > drempel for bedrag in bedragen) or totaal > drempel
        return {
            "regels": regels,
            "overgeslagen": overgeslagen,
            "totaal_cents": totaal,
            "drempel_cents": drempel,
            "vier_ogen_vereist": vier_ogen,
            "waarom": self._waarom(len(regels), totaal, drempel, vier_ogen, eerder_verlopen),
        }

    @staticmethod
    async def _laatste_voorstel_verlopen(session: AsyncSession, tenant_id: int) -> bool:
        """Is het LAATSTE betaalvoorstel van deze tenant niet op tijd beoordeeld (verlopen, ook als de opruimtaak nog niet draaide)?

        Dan krijgt het nieuwe voorstel de zin "eerder voorgelegd, niet op tijd beoordeeld". Alleen het laatste voorstel telt: een verlopen
        voorstel van weken geleden waarna alles gewoon is afgehandeld zegt niets over dit voorstel. Na het opruimen is de payload van een
        verlopen ticket leeg, dus de facturen zelf zijn hier niet te vergelijken; de status en de verlooptijd zijn genoeg.
        """
        nu = datetime.now(timezone.utc)
        rij = (
            await session.execute(
                select(HITLTicket.status, HITLTicket.expires_at)
                .where(HITLTicket.tenant_id == tenant_id, HITLTicket.tool_name == TOOL_NAME)
                .order_by(HITLTicket.id.desc())
                .limit(1)
            )
        ).first()
        if rij is None:
            return False
        return rij[0] == "expired" or (rij[0] == "pending" and rij[1] is not None and rij[1] < nu)

    @staticmethod
    def _waarom(
        aantal: int, totaal: int, drempel: int, vier_ogen: bool, eerder_verlopen: bool = False
    ) -> str:
        tekst = (
            f"De crediteurenagent stelt voor {aantal} {'factuur' if aantal == 1 else 'facturen'} te betalen, "
            f"samen {_euro(totaal)}: facturen die binnen {HORIZON_DAGEN} dagen vervallen of al te laat zijn, van bekende "
            "leveranciers met een geldig IBAN, die niet al in een ander voorstel staan."
        )
        if vier_ogen:
            tekst += (
                f" Een factuur of het totaal komt boven {_euro(drempel)}: dan moet iemand anders dan wie dit voorstel liet "
                "maken het goedkeuren (vier ogen)."
            )
        if eerder_verlopen:
            tekst += " Het vorige voorstel is eerder voorgelegd, niet op tijd beoordeeld; daarom komt dit opnieuw."
        return tekst

    @staticmethod
    async def _tenant_settings(session: AsyncSession, tenant_id: int) -> object:
        from src.core.models.rbac_models import Tenant

        return (
            await session.execute(select(Tenant.settings).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()

    @staticmethod
    async def _al_voorgesteld(session: AsyncSession, tenant_id: int) -> set[int]:
        """De facturen die al in een OPENSTAAND voorstel van DEZE tenant staan.

        Een `pending` ticket voorbij zijn verlooptijd blijft in de database `pending` tot een opruimtaak hem sluit, maar de backend weigert dan
        al het goedkeuren (`HITLTicketRepository.approve` filtert op `expires_at`): hij telt dus niet meer mee. Anders zitten zijn facturen
        voor altijd vast in een voorstel dat niemand meer kan beslissen (Gate 2).
        """
        nu = datetime.now(timezone.utc)
        rijen = await session.execute(
            select(HITLTicket.payload).where(
                HITLTicket.tenant_id == tenant_id,
                HITLTicket.tool_name == TOOL_NAME,
                or_(
                    and_(HITLTicket.status == "pending", HITLTicket.expires_at > nu),
                    and_(HITLTicket.status == "approved", HITLTicket.resolved_at > nu - _APPROVED_VENSTER),
                ),
            )
        )
        gezien: set[int] = set()
        for payload in rijen.scalars().all():
            regels = payload.get("regels") if isinstance(payload, dict) else None
            for regel in regels if isinstance(regels, list) else []:
                waarde = regel.get("payable_id") if isinstance(regel, dict) else None
                if isinstance(waarde, int) and not isinstance(waarde, bool):
                    gezien.add(waarde)
        return gezien

    # -- de tool (na goedkeuren) --------------------------------------------------------------------

    async def execute_payment_run_tool(
        self, tool_name: str, payload: dict[str, object], *, tenant_id: int
    ) -> dict[str, object]:
        """Voer het goedgekeurde voorstel uit. Geeft altijd een dict; gooit alleen bij onbekend/infra."""
        if tool_name not in self._TOOL_NAMES:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail=f"Payment run tool '{tool_name}' is not implemented",
            )
        self._controleer_tenant(tenant_id, tool_name)
        return await self._voer_uit(tenant_id, payload)

    async def _voer_uit(self, tenant_id: int, payload: dict[str, object]) -> dict[str, object]:
        from src.core.tool_broker.redaction import BROKER_INJECTED_KEYS

        # Servermetadata (`_`) en de sleutels die de broker zelf uit de executiecontext zet (`tenant_id`, `user_id`) tellen niet mee.
        onbekend = sorted(
            k
            for k in payload
            if k not in _VELDEN and not k.startswith("_") and k not in BROKER_INJECTED_KEYS
        )
        if onbekend:
            return {"success": False, "error": f"onbekende velden: {', '.join(onbekend)}"}
        regels = payload.get("regels")
        ticket_ref = payload.get("_hitl_ticket_ref")
        if not isinstance(regels, list) or not regels or not isinstance(ticket_ref, str):
            return {
                "success": False,
                "error": "Het voorstel of het ticket ontbreekt.",
                "reden_code": "voorstel_niet_uitvoerbaar",
            }
        geldig = [r for r in regels if isinstance(r, dict) and all(k in r for k in _REGEL_VELDEN)]
        if len(geldig) != len(regels):
            return {
                "success": False,
                "error": "Het voorstel bevat een onvolledige regel.",
                "reden_code": "voorstel_niet_uitvoerbaar",
            }
        ids = [r["payable_id"] for r in geldig]
        if not all(isinstance(i, int) and not isinstance(i, bool) for i in ids) or len(
            set(ids)
        ) != len(ids):
            return {
                "success": False,
                "error": "Het voorstel bevat een factuur twee keer of een ongeldig nummer.",
                "reden_code": "voorstel_niet_uitvoerbaar",
            }
        payable_ids = [int(str(i)) for i in ids]
        async with self._tenant_sessie(tenant_id) as session:
            door = (
                await session.execute(
                    select(HITLTicket.resolved_by).where(
                        HITLTicket.ticket_ref == ticket_ref, HITLTicket.tenant_id == tenant_id
                    )
                )
            ).scalar_one_or_none()
            fout = await self._controleer_regels(session, tenant_id, geldig, payable_ids)
            if fout is not None:
                await session.rollback()
                return {"success": False, "error": fout[1], "reden_code": fout[0]}
            gedaan = await PayableRepository(session).keur_goed_voor_betaling(
                tenant_id, payable_ids, door=door
            )
            if len(gedaan) != len(payable_ids):
                await session.rollback()
                return {
                    "success": False,
                    "error": "Een of meer facturen zijn intussen al goedgekeurd of aangepast; er is niets goedgekeurd. "
                    "Vraag de crediteurenagent om een nieuw voorstel.",
                    "reden_code": "factuur_niet_meer_te_betalen",
                }
            # De eigen binding van de run: welke facturen dit voorstel goedkeurde. `approve` laat van de payload alleen een digest over,
            # dus zonder dit is later niet te zeggen WELKE facturen een goedgekeurd voorstel waren (en dus ook niet in te trekken).
            # Zelfde transactie als het goedkeuren; een `_`-sleutel telt niet mee in de binding en staat niet in `tool_input`.
            await session.execute(
                update(HITLTicket)
                .where(HITLTicket.ticket_ref == ticket_ref, HITLTicket.tenant_id == tenant_id)
                .values(
                    payload=HITLTicket.payload.op("||")(
                        func.jsonb_build_object(
                            literal(RUN_FACTUREN_SLEUTEL), cast(literal(json.dumps(payable_ids)), JSONB)
                        )
                    )
                )
            )
            await session.commit()
            totaal = sum(int(str(r["amount_cents"])) for r in geldig)
            await self._audit(
                session,
                tenant_id,
                "payment_run_approved",
                f"payment_run_approved: {len(payable_ids)} facturen via ticket {ticket_ref}",
                {
                    "ticket_ref": ticket_ref,
                    "aantal": len(payable_ids),
                    "totaal_cents": totaal,
                    "payable_ids": payable_ids,
                    "approved_by": door,
                },
                user_id=door,
            )
        return {"success": True, "aantal": len(payable_ids), "totaal_cents": totaal}

    @staticmethod
    async def _controleer_regels(
        session: AsyncSession,
        tenant_id: int,
        regels: list[dict[str, object]],
        payable_ids: list[int],
    ) -> tuple[str, str] | None:
        """Klopt elke regel nog met wat de goedkeurder zag? `(code, tekst)` bij de eerste afwijking, anders `None`.

        De code (`uitvoerredenen.UITVOERREDENEN`) gaat naar de goedkeurder als vaste zin; de tekst is voor het log en bevat het nummer.
        """
        rijen = (
            (
                await session.execute(
                    select(Payable)
                    .where(Payable.tenant_id == tenant_id, Payable.id.in_(payable_ids))
                    .with_for_update(of=Payable)
                )
            )
            .unique()
            .scalars()
            .all()
        )
        per_id = {int(r.id): r for r in rijen}
        for regel in regels:
            rij = per_id.get(int(str(regel["payable_id"])))
            nummer = regel["invoice_number"]
            if rij is None:
                return "factuur_bestaat_niet_meer", f"Factuur {nummer} bestaat niet meer; er is niets goedgekeurd."
            if rij.status not in _TE_BETALEN:
                return (
                    "factuur_niet_meer_te_betalen",
                    f"Factuur {nummer} staat al op status {rij.status}; er is niets goedgekeurd.",
                )
            if (
                int(rij.amount_cents) != regel["amount_cents"]
                or rij.currency != "EUR"
                or int(rij.supplier_id) != regel["supplier_id"]
                or rij.due_date.isoformat() != regel["due_date"]
                # Wat de goedkeurder LEEST (naam en nummer) moet ook kloppen: een ticket dat niet van de agent komt kan er andere tekst
                # in zetten dan de rij heeft.
                or rij.invoice_number != regel["invoice_number"]
                or rij.supplier.name != regel["supplier_name"]
            ):
                return (
                    "factuur_veranderd",
                    f"Factuur {nummer} is veranderd sinds het voorstel werd gemaakt; er is niets goedgekeurd.",
                )
            iban = probeer_iban(rij.supplier.iban)
            if iban is None or iban_digest(tenant_id, iban) != regel["iban_digest"]:
                return (
                    "iban_gewijzigd",
                    f"Het IBAN van de leverancier van factuur {nummer} is veranderd sinds het voorstel; "
                    "er is niets goedgekeurd.",
                )
        return None

    # -- intrekken na goedkeuren (crediteuren nazorg, punt 2) -----------------------------------------

    async def trek_factuur_in(
        self, tenant_id: int, payable_id: int, *, door: int, reden: str
    ) -> dict[str, object] | None:
        """Trek een goedgekeurde factuur in (`afgewezen`), zolang hij in geen betaalbestand zit. `None` als de factuur hier niet bestaat.

        De reden is verplicht (de route controleert de lengte) en komt in de auditregel `payable_withdrawn`. De statusovergang is een
        atomaire UPDATE met `goedgekeurd` in de WHERE: een factuur die intussen in een bestand kwam, wordt niet aangeraakt.
        """
        self._controleer_tenant(tenant_id)
        async with self._tenant_sessie(tenant_id) as session:
            repo = PayableRepository(session)
            rij = await repo.get(tenant_id, payable_id)
            if rij is None:
                return None
            huidig = str(rij.status)
            nummer = str(rij.invoice_number)
            if huidig != "goedgekeurd":
                await session.rollback()
                raise ValidatieFout(self._intrekken_geweigerd(huidig))
            gedaan = await repo.trek_goedkeuring_in(tenant_id, [payable_id], naar="afgewezen")
            if not gedaan:
                await session.rollback()
                raise ValidatieFout(self._intrekken_geweigerd("in_betaalbestand"))
            # Schoonmaken VOOR de commit: faalt dat onverwacht, dan is er niets ingetrokken in plaats van een 500 na een vastgelegd besluit.
            reden_schoon = _schoon(reden)
            await session.commit()
            await self._audit(
                session,
                tenant_id,
                "payable_withdrawn",
                f"payable_withdrawn: factuur {payable_id} ingetrokken na goedkeuring",
                {"payable_id": payable_id, "invoice_number": nummer, "reden": reden_schoon, "withdrawn_by": door},
                user_id=door,
            )
        return {"payable_id": payable_id, "status": "afgewezen"}

    async def trek_voorstel_in(
        self, tenant_id: int, *, ticket_ref: str, door: int, reden: str
    ) -> dict[str, object] | None:
        """Trek een goedgekeurd betaalvoorstel in zolang het betaalbestand nog niet is gemaakt; de facturen komen vrij (`gecontroleerd`).

        Welke facturen bij het voorstel horen staat in het ticket zelf (`RUN_FACTUREN_SLEUTEL`, gezet bij het goedkeuren), niet in het
        auditlog: dat is een verslag en best-effort. `None` als het ticket hier niet bestaat.
        """
        self._controleer_tenant(tenant_id)
        async with self._tenant_sessie(tenant_id) as session:
            ticket = (
                await session.execute(
                    select(HITLTicket).where(
                        HITLTicket.ticket_ref == ticket_ref, HITLTicket.tenant_id == tenant_id
                    )
                )
            ).scalar_one_or_none()
            if ticket is None:
                return None
            ids = ticket.payload.get(RUN_FACTUREN_SLEUTEL) if isinstance(ticket.payload, dict) else None
            if isinstance(ticket.payload, dict) and ticket.payload.get(RUN_INGETROKKEN_SLEUTEL):
                await session.rollback()
                raise ValidatieFout("Dit voorstel is al ingetrokken.")
            if (
                ticket.tool_name != TOOL_NAME
                or ticket.status not in ("approved", "consumed")
                or not isinstance(ids, list)
                or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids)
            ):
                await session.rollback()
                raise ValidatieFout(
                    "Dit is geen goedgekeurd betaalvoorstel waarvan bekend is welke facturen erbij horen. "
                    "Trek de facturen een voor een in op de pagina Crediteuren."
                )
            repo = PayableRepository(session)
            alle_ids = [int(str(i)) for i in ids]
            vrij = await repo.trek_goedkeuring_in(tenant_id, alle_ids, naar="gecontroleerd")
            statussen = {
                str(s)
                for s in (
                    await session.execute(
                        select(Payable.status).where(Payable.tenant_id == tenant_id, Payable.id.in_(alle_ids))
                    )
                ).scalars()
            }
            # Zit ook maar een factuur van dit voorstel al in een betaalbestand (bijvoorbeeld door een gelijktijdig betaalbestand), dan
            # gaat niets terug: een voorstel dat half is ingetrokken zou de gebruiker laten denken dat alles is vrijgegeven.
            if statussen & {"in_betaalbestand", "betaald"}:
                await session.rollback()
                raise ValidatieFout(self._intrekken_geweigerd("in_betaalbestand"))
            if not vrij:
                await session.rollback()
                raise ValidatieFout("Dit voorstel is al ingetrokken: er staat geen enkele factuur meer op goedgekeurd.")
            reden_schoon = _schoon(reden)
            # Markeer het ticket in dezelfde transactie: de binding gaat eruit en `ingetrokken` erin, zodat een tweede intrekking op deze
            # ticketverwijzing niets meer kan vrijgeven (ook niet de facturen van een nieuwer voorstel).
            await session.execute(
                update(HITLTicket)
                .where(HITLTicket.ticket_ref == ticket_ref, HITLTicket.tenant_id == tenant_id)
                .values(
                    payload=HITLTicket.payload.op("-")(literal(RUN_FACTUREN_SLEUTEL)).op("||")(
                        func.jsonb_build_object(literal(RUN_INGETROKKEN_SLEUTEL), cast(literal("true"), JSONB))
                    )
                )
            )
            await session.commit()
            await self._audit(
                session,
                tenant_id,
                "payment_run_withdrawn",
                f"payment_run_withdrawn: {len(vrij)} facturen vrijgegeven uit ticket {ticket_ref}",
                {"ticket_ref": ticket_ref, "payable_ids": vrij, "reden": reden_schoon, "withdrawn_by": door},
                user_id=door,
            )
        return {"ticket_ref": ticket_ref, "aantal": len(vrij), "payable_ids": vrij}

    @staticmethod
    def _intrekken_geweigerd(status: str) -> str:
        """De Nederlandse reden waarom een factuur niet meer in te trekken is."""
        if status in ("in_betaalbestand", "betaald"):
            return (
                "Deze factuur zit al in een betaalbestand en kan niet meer worden ingetrokken: het bestand wordt eenmalig gemaakt. "
                "Is er al betaald of wordt er betaald, regel het dan met de bank."
            )
        if status == "afgewezen":
            return "Deze factuur is al ingetrokken of afgewezen."
        return "Alleen een goedgekeurde factuur kan worden ingetrokken."

    # -- het betaalbestand ---------------------------------------------------------------------------

    async def maak_betaalbestand(
        self,
        tenant_id: int,
        *,
        door: int,
        debiteur_naam: str,
        debiteur_iban: str,
        uitvoerdatum: date,
        vandaag: date | None = None,
    ) -> tuple[bytes, dict[str, object]]:
        """Zet ALLE goedgekeurde facturen van de tenant in een pain.001-bestand en op `in_betaalbestand`; een keer, atomair.

        Mislukt het bouwen (ongeldig IBAN, datum in het verleden), dan draait alles
        terug en blijven de facturen `goedgekeurd`. Een factuur waarvan de leverancier na de goedkeuring is gewijzigd gaat NIET mee en wordt
        teruggezet naar `gecontroleerd` (voor een nieuw voorstel); de overige facturen krijgen wel hun bestand. Geeft het bestand en `{aantal, totaal_cents, bericht_id}`.
        """
        self._controleer_tenant(tenant_id)
        nu = datetime.now(timezone.utc)
        async with self._tenant_sessie(tenant_id) as session:
            rijen = await PayableRepository(session).claim_voor_betaalbestand(tenant_id)
            if not rijen:
                await session.rollback()
                raise ValidatieFout(
                    "Er zijn geen goedgekeurde facturen om in een betaalbestand te zetten. Een factuur zit in hooguit "
                    "een betaalbestand."
                )
            # Twee verschillende leveranciers op een IBAN: niets wordt betaald. Dat kan niet meer via de repository ontstaan (die weigert het),
            # maar bestond misschien al of ontstond door twee gelijktijdige invoeren. Het bestand legt het voor in plaats van stil te betalen.
            per_iban: dict[str, dict[int, str]] = {}
            for rij in rijen:
                gelezen = probeer_iban(rij.supplier.iban)
                if gelezen is not None:
                    per_iban.setdefault(gelezen, {})[int(rij.supplier_id)] = str(rij.supplier.name)
            dubbel = next((namen for namen in per_iban.values() if len(namen) > 1), None)
            if dubbel is not None:
                genoemd = " en ".join(sorted(dubbel.values()))
                await session.rollback()
                raise ValidatieFout(
                    f"De leveranciers {genoemd} hebben hetzelfde IBAN. Er is geen betaalbestand gemaakt en er is niets betaald. "
                    "Controleer welke leverancier bij dit IBAN hoort, pas het IBAN van de ander aan en haal daarna het bestand opnieuw op."
                )
            regels: list[BetaalRegel] = []
            overgeslagen: list[dict[str, object]] = []
            terugzetten: list[Payable] = []
            for rij in rijen:
                leverancier = rij.supplier
                if rij.checked_at is None or leverancier.updated_at > rij.checked_at:
                    # Een factuur waarvan de leverancier na de goedkeuring is gewijzigd gaat NIET mee (het IBAN is niet meer wat de goedkeurder
                    # zag), maar houdt de rest niet tegen: hij blijft `goedgekeurd`. Het nummer nu lezen: na een rollback zijn de objecten
                    # verlopen en vraagt elke attribuuttoegang de database (buiten de sessie: MissingGreenlet).
                    overgeslagen.append(
                        {
                            "invoice_number": rij.invoice_number,
                            "reden": "de leverancier is gewijzigd na de goedkeuring; teruggezet voor een nieuw voorstel",
                        }
                    )
                    terugzetten.append(rij)
                    continue
                regels.append(
                    BetaalRegel(
                        payable_id=int(rij.id),
                        naam=leverancier.name,
                        iban=leverancier.iban or "",
                        bedrag_cents=int(rij.amount_cents),
                        factuurnummer=rij.invoice_number,
                    )
                )
            # Een factuur waarvan de leverancier is gewijzigd gaat terug naar `gecontroleerd`: de agent kan hem dan opnieuw voorstellen en
            # een mens keurt hem opnieuw goed, nu met het nieuwe IBAN in beeld. Zonder deze stap bleef hij voor altijd `goedgekeurd`
            # (`updated_at` blijft later dan `checked_at`) en gaf elke volgende download dezelfde melding (Gate 2, code 1).
            for rij in terugzetten:
                rij.status = "gecontroleerd"
            if not regels:
                nummers = ", ".join(str(o["invoice_number"]) for o in overgeslagen)
                # Het terugzetten blijft staan; er is alleen geen bestand.
                await session.commit()
                raise ValidatieFout(
                    f"De leverancier van factuur {nummers} is gewijzigd na de goedkeuring. Er is geen betaalbestand gemaakt. "
                    "De factuur is teruggezet voor een nieuw betaalvoorstel: laat de agent opnieuw voorstellen en keur het "
                    "voorstel opnieuw goed, nu met het nieuwe IBAN."
                )
            if terugzetten:
                await session.flush()
            bericht_id = f"CRD{nu:%Y%m%d%H%M%S}{secrets.token_hex(4)}"
            try:
                bestand = maak_pain001(
                    Betaalopdracht(
                        bericht_id=bericht_id,
                        gemaakt_op=nu,
                        uitvoerdatum=uitvoerdatum,
                        debiteur_naam=debiteur_naam,
                        debiteur_iban=debiteur_iban,
                        regels=regels,
                    ),
                    vandaag=vandaag,
                )
            except (ValidatieFout, TypeError):
                await session.rollback()
                raise
            await session.commit()
            totaal = sum(r.bedrag_cents for r in regels)
            await self._audit(
                session,
                tenant_id,
                "payment_file_created",
                f"payment_file_created: {len(regels)} facturen in bericht {bericht_id}",
                {
                    "bericht_id": bericht_id,
                    "aantal": len(regels),
                    "totaal_cents": totaal,
                    "payable_ids": [r.payable_id for r in regels],
                    "overgeslagen": [str(o["invoice_number"]) for o in overgeslagen],
                    # Het bestand zelf wordt niet bewaard; met deze vingerafdruk is later te zien of een bestand dat iemand in de bank
                    # laadt precies dit bestand is.
                    "bestand_sha256": hashlib.sha256(bestand).hexdigest(),
                    "created_by": door,
                },
                user_id=door,
            )
        return bestand, {
            "aantal": len(regels),
            "totaal_cents": totaal,
            "bericht_id": bericht_id,
            "overgeslagen": overgeslagen,
        }

    # -- auditregel ----------------------------------------------------------------------------------

    async def schrijf_audit(
        self,
        tenant_id: int,
        event_type: str,
        description: str,
        details: dict[str, object],
    ) -> None:
        """Een auditregel van de crediteurenagent, best-effort in een eigen sessie van DEZE tenant (voor de skill)."""
        self._controleer_tenant(tenant_id)
        async with self._tenant_sessie(tenant_id) as session:
            await self._audit(session, tenant_id, event_type, description, details)

    @staticmethod
    async def _audit(
        session: AsyncSession,
        tenant_id: int,
        event_type: str,
        description: str,
        details: dict[str, object],
        user_id: int | None = None,
    ) -> None:
        """Best-effort NA de commit van de rij; geen IBAN in de details, alleen nummers en bedragen."""
        from src.core.utils.best_effort import best_effort

        audit = importlib.import_module("src.core.governance.services.audit_service").AuditService
        async with best_effort(f"auditregel {event_type} voor crediteuren", db_session=session):
            await audit.log_event(
                db=session,
                event_type=event_type,
                severity="medium",
                source_ip="agent",
                endpoint="/agents/crediteuren",
                description=description,
                user_id=user_id,
                tenant_id=tenant_id,
                action=event_type,
                resource="crediteuren",
                metadata=dict(details),
            )
            await session.commit()


async def vier_ogen_nodig(session: AsyncSession, tenant_id: int, regels: object) -> bool:
    """Moet iemand ANDERS dan de aanvrager dit voorstel goedkeuren? Beslist uit de DATABASE, nooit uit wat het ticket zegt.

    Waar een betaalvoorstel altijd van de agent komt, kan een gebruiker met een eigen ticket (`POST /hitl/request`) in `tool_input` een
    vlag zetten die zegt dat vier ogen niet nodig is (Gate 2, security 1). Daarom leest de HITL-route de bedragen en het drempelbedrag
    zelf en gebruikt de vlag in het ticket alleen om te tonen. Vier ogen geldt zodra een factuur OF het totaal van het voorstel BOVEN het drempelbedrag komt.

    Fail-secure: een voorstel zonder leesbare regels, met een onbekend factuurnummer of een factuur die niet (meer) van deze tenant is,
    vraagt vier ogen.
    """
    if not isinstance(regels, list) or not regels:
        return True
    ids: set[int] = set()
    for regel in regels:
        waarde = regel.get("payable_id") if isinstance(regel, dict) else None
        if not isinstance(waarde, int) or isinstance(waarde, bool):
            return True
        ids.add(waarde)
    drempel = drempel_uit_settings(await BetaalrunToolRegistry._tenant_settings(session, tenant_id))
    bedragen = (
        await session.execute(
            select(Payable.id, Payable.amount_cents).where(
                Payable.tenant_id == tenant_id, Payable.id.in_(ids)
            )
        )
    ).all()
    if len(bedragen) != len(ids):
        return True
    bedragen_in_centen = [int(bedrag) for _id, bedrag in bedragen]
    return any(b > drempel for b in bedragen_in_centen) or sum(bedragen_in_centen) > drempel
