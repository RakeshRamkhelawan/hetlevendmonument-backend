"""Crediteurentools voor de crediteurenagent: `record_supplier_invoice` en `propose_supplier_invoice` (crediteuren dag 2).

Gemodelleerd naar `receivables_registry.py`: een tenant-gescoped brug tussen een ToolBroker-payload en de database. De tenant komt als
los argument van de broker (uit de executiecontext), nooit uit de payload.

**Twee tools, twee risicoklassen.** De agent leest een door de bonlezer gelezen inkoopfactuur en beoordeelt hem (`beoordeel`, een
LEESpad dat de skill rechtstreeks gebruikt, zoals `DunningSkill._tel_openstaand`):

- `record_supplier_invoice` (MEDIUM): het SCHONE geval. Een bekende leverancier, een IBAN dat gelijk is aan het bekende, geen dubbele
  factuur en alle velden zeker. De tool beoordeelt zelf OPNIEUW en weigert als de factuur niet schoon is: de agent kan dit pad dus niet
  gebruiken om een uitzondering stil vast te leggen. Vastleggen betaalt niets; betalen is dag 4.
- `propose_supplier_invoice` (HIGH): elke UITZONDERING. De HITL-poort van de broker maakt er een ticket van met het waarom; pas na
  goedkeuren komt de tool hier aan en legt hij vast, en maakt bij een nieuwe leverancier die leverancier aan. Ook hier wordt opnieuw
  beoordeeld en weigert de tool als wat de mens zag niet meer klopt (de factuur of de leverancier is intussen veranderd, het is een
  dubbele geworden, of er ontbreken gegevens: dan is aanpassen de enige route).

**Het IBAN van een bekende leverancier verandert nooit stil.** Een afwijkend IBAN is een bekende fraudevorm. Het gaat altijd langs een
mens en wordt pas na een goedgekeurd ticket gezet.

**Een upload wordt hooguit een keer een factuur**: `FactuurKoppeling` (`als/bonlezer/factuur.py`) legt per upload beslag; het ticket en de
uitvoering na goedkeuren horen bij dezelfde claim.

**Tekst van een factuur is vijandige invoer.** Naam en factuurnummer komen straks in een betaalbestand en in een brief; stuurtekens,
onzichtbare tekens en regel- of alineascheiders (Unicode Cc, Cf, Zl, Zp) maken het veld "onzeker" in plaats van het schoon te knippen,
net als de API-schema's (`payables/schemas.py`) die weigeren.

Een tool geeft geen persoonsgegevens terug (het resultaat gaat de event bus op): alleen `success` en het nummer van de factuur.
"""

from __future__ import annotations

import asyncio
import importlib
import unicodedata
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidatieFout
from src.core.repositories.payable_repository import (
    NewPayable,
    IbanAlInGebruik,
    NewSupplier,
    PayableRepository,
    SupplierRepository,
    probeer_iban,
)
from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.hitl_repository import HITLTicketRepository
from src.core.tool_broker.models import HITLTicket

RECORD_TOOL_NAME = "record_supplier_invoice"
PROPOSE_TOOL_NAME = "propose_supplier_invoice"

_RECORD_FIELDS = frozenset({"bestand_id"})
#: Wat de mens in het ticket ziet en goedkeurt. Alles komt uit de BEOORDELING, nooit van het model.
_PROPOSE_FIELDS = frozenset(
    {
        "bestand_id",
        "supplier_id",
        "supplier_name",
        "iban",
        "bekend_iban",
        "invoice_number",
        "amount_cents",
        "currency",
        "invoice_date",
        "due_date",
        "factuur_naam",
        "iban_wijkt_af",
        "goedkeuren_mogelijk",
        "waarom",
    }
)
#: De velden die bij het goedkeuren nog gelijk moeten zijn aan wat de beoordeling NU geeft.
_FEITSLEUTELS = (
    "supplier_id",
    "supplier_name",
    "iban",
    "bekend_iban",
    "invoice_number",
    "amount_cents",
    "currency",
    "invoice_date",
    "due_date",
    "factuur_naam",
    "iban_wijkt_af",
    "goedkeuren_mogelijk",
)

#: Een factuur van meer dan dit bedrag is vrijwel zeker een leesfout; zelfde grens als `payables/schemas.py`.
_MAX_BEDRAG_CENTEN = 100_000_000_000
#: Unicode-categorieen die in een naam of nummer niets te zoeken hebben (zie de moduledocstring).
_VERBODEN_CATEGORIEEN = frozenset({"Cc", "Cf", "Zl", "Zp"})

_MELDING_DUBBEL = "Deze factuur van deze leverancier is al vastgelegd."


class _Dienst(Protocol):
    """Wat deze registry van `BonDienst` gebruikt; een Protocol zodat `tool_broker` niet statisch naar `als` koppelt."""

    @property
    def root(self) -> object: ...

    def soort(self, tenant_id: int, bestand_id: str) -> str | None: ...

    def naam(self, tenant_id: int, bestand_id: str) -> str | None: ...

    def status(self, tenant_id: int, bestand_id: str) -> dict[str, object]: ...


class _Koppeling(Protocol):
    def lees(self, tenant_id: int, bestand_id: str) -> dict[str, object] | None: ...

    def claim(self, tenant_id: int, bestand_id: str) -> bool: ...

    def schrijf(self, tenant_id: int, bestand_id: str, record: dict[str, object]) -> None: ...

    def geef_vrij(self, tenant_id: int, bestand_id: str) -> None: ...

    def was_eerder_verlopen(self, tenant_id: int, bestand_id: str) -> bool: ...

    def leg_vast(
        self, tenant_id: int, bestand_id: str, payable_id: int, *, door: int | None
    ) -> None: ...


@asynccontextmanager
async def _default_session_factory() -> AsyncGenerator[AsyncSession, None]:
    """Standaard sessie via de centrale DB-manager, net als de debiteuren-registry."""
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        yield session


def _bon_dienst() -> _Dienst:
    """De echte bonlezer-dienst. Lazy en via `importlib`: een statische import vanuit `tool_broker` naar `als` telt mee in de koppeling."""
    return cast(_Dienst, importlib.import_module("src.core.als.bonlezer.dienst").maak_dienst())


def _koppeling(dienst: _Dienst) -> _Koppeling:
    factuur = importlib.import_module("src.core.als.bonlezer.factuur")
    return cast(_Koppeling, factuur.FactuurKoppeling(dienst.root))


def _onbekende_velden(payload: dict[str, object], vocabulaire: frozenset[str]) -> list[str]:
    """Sleutels die de tool niet kent; servermetadata (`_`) en broker-sleutels tellen niet mee."""
    from src.core.tool_broker.redaction import BROKER_INJECTED_KEYS

    return sorted(
        k
        for k in payload
        if not k.startswith("_") and k not in vocabulaire and k not in BROKER_INJECTED_KEYS
    )


def maskeer_iban(iban: object) -> str | None:
    """`NL91ABNA0417164300` wordt `NL91ABNA******4300`: land, controlegetal, bankcode en de laatste vier tekens blijven zichtbaar.

    De inhoudswachter van de agent (`governance/input_guard.py`) BLOKKEERT elk geldig IBAN in de parameters van een tool; die vloer
    mag niet worden versmald. Het ticket toont dus een gemaskeerd IBAN: genoeg om een ander bankje of een ander nummer te zien,
    niet genoeg om te betalen. Het volledige IBAN blijft in de upload en in `suppliers`; de tool vergelijkt en legt vast met dat
    volledige nummer, nooit met wat in het ticket staat.
    """
    if not isinstance(iban, str) or len(iban) < 13:
        return None
    return iban[:8] + "*" * (len(iban) - 12) + iban[-4:]


def _datum(waarde: object) -> date | None:
    if not isinstance(waarde, str):
        return None
    try:
        return date.fromisoformat(waarde)
    except ValueError:
        return None


def _centen(waarde: object) -> int | None:
    """`"1210.00"` wordt 121000; geen geheel aantal centen, nul of onzinnig groot geeft `None` (onzeker, niet afgerond)."""
    if not isinstance(waarde, str):
        return None
    try:
        bedrag = Decimal(waarde) * 100
    except InvalidOperation:
        return None
    if bedrag != bedrag.to_integral_value() or not 0 < bedrag <= _MAX_BEDRAG_CENTEN:
        return None
    return int(bedrag)


def _btw_boven_totaal(velden: dict[object, object], centen: int | None) -> bool:
    """Meer btw dan totaal is een leesfout (zelfde controle als bij een bon)."""
    btw = velden.get("btw")
    if centen is None or not isinstance(btw, dict):
        return False
    try:
        som = sum((Decimal(str(bedrag)) for bedrag in btw.values()), Decimal(0)) * 100
    except InvalidOperation:
        return True
    return bool(som > centen)


def _naamsleutel(naam: str) -> str:
    """Een naam zonder hoofdletters, leestekens en spaties (NFKC): `Acme B.V.` en `ACME BV` zijn dezelfde sleutel."""
    return "".join(teken for teken in unicodedata.normalize("NFKC", naam).casefold() if teken.isalnum())


def _tekst(waarde: object, maximum: int) -> str | None:
    """Een naam of nummer zonder stuurtekens; `None` (onzeker) als er een verboden teken in zit of er niets overblijft."""
    if not isinstance(waarde, str):
        return None
    schoon = " ".join(waarde.split())
    if not schoon or any(unicodedata.category(teken) in _VERBODEN_CATEGORIEEN for teken in schoon):
        return None
    return schoon[:maximum]


class PayablesToolRegistry:
    """Voert de crediteurentools uit en beoordeelt een gelezen factuur, altijd binnen EEN tenant."""

    _TOOL_NAMES = frozenset({RECORD_TOOL_NAME, PROPOSE_TOOL_NAME})

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
    ) -> None:
        self._session_factory = session_factory or _default_session_factory

    @classmethod
    def known_tool_names(cls) -> set[str]:
        """De toolnamen die deze registry afhandelt."""
        return set(cls._TOOL_NAMES)

    def koppeling(self) -> _Koppeling:
        """De koppeling tussen een upload en de factuur die eruit komt (voor de skill: claim en stand van een upload)."""
        return _koppeling(_bon_dienst())

    # -- sessie -------------------------------------------------------------------------------------

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

    # -- de beoordeling (LEESpad) -------------------------------------------------------------------

    async def ticket_is_verlopen(self, tenant_id: int, ticket_ref: str) -> bool:
        """Is dit ticket niet op tijd beoordeeld? Telt bij het LEZEN, ook als de uurlijkse opruimtaak nog niet draaide.

        Een ticket dat nog `pending` is maar zijn termijn voorbij is, wordt hier meteen op `expired` gezet (de opruimtaak zou het
        straks ook doen), zodat het niet als openstaand blijft staan. Een goedgekeurd, afgewezen of onbekend ticket is niet verlopen.
        """
        self._controleer_tenant(tenant_id)
        async with self._tenant_sessie(tenant_id) as session:
            rij = (
                await session.execute(
                    select(HITLTicket.status, HITLTicket.expires_at).where(
                        HITLTicket.ticket_ref == ticket_ref, HITLTicket.tenant_id == tenant_id
                    )
                )
            ).first()
            if rij is None:
                return False
            if rij[0] == "expired":
                return True
            if rij[0] == "pending" and rij[1] is not None and rij[1] < datetime.now(timezone.utc):
                await HITLTicketRepository(session).cleanup_expired(tenant_id)
                await session.commit()
                return True
            return False

    async def beoordeel(self, tenant_id: int, bestand_id: str) -> dict[str, object]:
        """Lees het resultaat van de bonlezer voor deze upload en zeg wat er mee moet gebeuren.

        `uitkomst`: `schoon`, `uitzondering` (met `redenen` en `waarom`), `dubbel` (met `reden`), `nog_niet_klaar`, `onleesbaar` of
        `onbekend` (de upload bestaat niet voor deze tenant). Legt niets vast. De feiten die de mens in het ticket ziet staan in `feiten`.
        """
        self._controleer_tenant(tenant_id)
        upload = importlib.import_module("src.core.als.bonlezer.upload")
        leeg: dict[str, object] = {"redenen": [], "waarom": "", "feiten": {}}
        if not upload.is_bestand_id(bestand_id):
            return {"uitkomst": "onbekend", **leeg}
        dienst = _bon_dienst()
        # Een bon van de bonnenpagina is geen inkoopfactuur: de agent pakt hem nooit op, ook niet als iemand zijn nummer kent.
        if await asyncio.to_thread(dienst.soort, tenant_id, bestand_id) != "factuur":
            return {"uitkomst": "onbekend", **leeg}
        try:
            status = dict(await asyncio.to_thread(dienst.status, tenant_id, bestand_id))
        except upload.BonNietGevonden:
            return {"uitkomst": "onbekend", **leeg}
        eindstand = status.get("status")
        if eindstand == "wachten":
            return {"uitkomst": "nog_niet_klaar", **leeg}
        velden = status.get("velden")
        if eindstand != "gelezen" or not isinstance(velden, dict):
            return {"uitkomst": "onleesbaar", **leeg}
        feiten, ontbrekend = self._feiten(velden)
        async with self._tenant_sessie(tenant_id) as session:
            gevonden = await SupplierRepository(session).find_match(
                tenant_id,
                naam=feiten["supplier_name"] if isinstance(feiten["supplier_name"], str) else None,
                iban=feiten["iban"] if isinstance(feiten["iban"], str) else None,
            )
            leverancier = gevonden[0] if gevonden else None
            gevonden_op = gevonden[1] if gevonden else None
            lijkt_op: str | None = None
            if leverancier is None and isinstance(feiten["supplier_name"], str):
                sleutel = _naamsleutel(feiten["supplier_name"])
                for bekende in await SupplierRepository(session).list_for_tenant(tenant_id, limit=1000):
                    if sleutel and _naamsleutel(bekende.name) == sleutel:
                        lijkt_op = bekende.name
                        break
            if leverancier is not None:
                feiten["factuur_naam"] = feiten["supplier_name"]
                feiten["supplier_id"] = leverancier.id
                feiten["supplier_name"] = leverancier.name
                feiten["bekend_iban"] = leverancier.iban
                nummer = feiten["invoice_number"]
                if isinstance(nummer, str) and await PayableRepository(session).find_duplicate(
                    tenant_id, leverancier.id, nummer
                ):
                    return {
                        "uitkomst": "dubbel",
                        "redenen": [],
                        "waarom": "",
                        "reden": _MELDING_DUBBEL,
                        "feiten": feiten,
                    }
        # De naam die de gebruiker de upload gaf is voor een mens begrijpelijk; het nummer van het bestand is dat niet.
        bron = _tekst(await asyncio.to_thread(dienst.naam, tenant_id, bestand_id), 80) or bestand_id
        redenen, zinnen = self._redenen(
            bron, feiten, ontbrekend, leverancier is not None, gevonden_op, lijkt_op
        )
        if redenen and _koppeling(dienst).was_eerder_verlopen(tenant_id, bestand_id):
            zinnen.insert(
                1, "Deze factuur is eerder voorgelegd, niet op tijd beoordeeld; daarom wordt hij opnieuw voorgelegd."
            )
        return {
            "uitkomst": "uitzondering" if redenen else "schoon",
            "redenen": redenen,
            "waarom": " ".join(zinnen),
            "feiten": feiten,
            "ticketfeiten": {
                **feiten,
                "iban": maskeer_iban(feiten["iban"]),
                "bekend_iban": maskeer_iban(feiten["bekend_iban"]),
                # De BACKEND zegt of het IBAN afwijkt: twee gemaskeerde nummers kunnen gelijk ogen terwijl de verborgen
                # cijfers verschillen, dus het scherm mag dat niet zelf uit de maskers afleiden (Gate 2).
                "iban_wijkt_af": "afwijkend_iban" in redenen,
                # Zonder alle velden of in een andere valuta kan goedkeuren niets vastleggen: het scherm toont dan geen
                # goedkeurknop (het ticket zou verbruikt worden zonder dat er iets gebeurt).
                "goedkeuren_mogelijk": "ontbrekend_veld" not in redenen and "andere_valuta" not in redenen,
            },
        }

    @staticmethod
    def _feiten(velden: dict[object, object]) -> tuple[dict[str, object], list[str]]:
        """De velden van de bonlezer als feiten voor het ticket, en welke ontbreken of onzeker zijn (Nederlandse namen)."""
        factuurdatum = _datum(velden.get("datum"))
        vervaldatum = _datum(velden.get("vervaldatum"))
        centen = _centen(velden.get("totaal"))
        valuta = velden.get("valuta")
        iban = velden.get("iban")
        feiten: dict[str, object] = {
            "supplier_id": None,
            "factuur_naam": None,
            "supplier_name": _tekst(velden.get("leverancier"), 200),
            "iban": iban if isinstance(iban, str) else None,
            "bekend_iban": None,
            "invoice_number": _tekst(velden.get("factuurnummer"), 100),
            "amount_cents": centen,
            "currency": valuta if isinstance(valuta, str) else None,
            "invoice_date": factuurdatum.isoformat() if factuurdatum else None,
            "due_date": vervaldatum.isoformat() if vervaldatum else None,
        }
        ontbrekend: list[str] = []
        if feiten["supplier_name"] is None:
            ontbrekend.append("naam van de leverancier")
        if feiten["invoice_number"] is None:
            ontbrekend.append("factuurnummer")
        if factuurdatum is None:
            ontbrekend.append("factuurdatum")
        if vervaldatum is None or (factuurdatum is not None and vervaldatum < factuurdatum):
            ontbrekend.append("vervaldatum")
        if centen is None or _btw_boven_totaal(velden, centen):
            ontbrekend.append("bedrag")
        if feiten["currency"] is None:
            ontbrekend.append("valuta")
        return feiten, ontbrekend

    @staticmethod
    def _redenen(
        bron: str,
        feiten: dict[str, object],
        ontbrekend: list[str],
        bekend: bool,
        gevonden_op: str | None = None,
        lijkt_op: str | None = None,
    ) -> tuple[list[str], list[str]]:
        """De redenen waarom een mens ernaar moet kijken, als codes en als Nederlandse zinnen voor het ticket."""
        redenen: list[str] = []
        zinnen: list[str] = [f"Bron: de geuploade factuur {bron!r}."]
        naam = feiten["supplier_name"]
        iban, bekend_iban = feiten["iban"], feiten["bekend_iban"]
        iban_getoond, bekend_getoond = maskeer_iban(iban), maskeer_iban(bekend_iban)
        if ontbrekend:
            redenen.append("ontbrekend_veld")
            zinnen.append(
                f"Niet gelezen of onzeker: {', '.join(ontbrekend)}. De agent raadt niet; "
                "pas de factuur aan via de bevestigroute."
            )
        if feiten["currency"] not in (None, "EUR"):
            redenen.append("andere_valuta")
            zinnen.append(f"De valuta is {feiten['currency']}; de agent verwerkt alleen euro's.")
        if not bekend:
            redenen.append("onbekende_leverancier")
            zinnen.append(
                f"De leverancier {naam!r} is nog niet bekend. Goedkeuren legt de leverancier "
                "en de factuur vast."
            )
            if lijkt_op is not None:
                redenen.append("lijkt_op_bekende_leverancier")
                zinnen.append(
                    f"De naam lijkt op die van de bekende leverancier {lijkt_op!r} maar is niet gelijk: controleer "
                    "of dit dezelfde leverancier is voordat u een nieuwe aanmaakt."
                )
        elif (
            isinstance(iban, str)
            and isinstance(bekend_iban, str)
            and probeer_iban(iban) != bekend_iban
        ):
            redenen.append("afwijkend_iban")
            zinnen.append(
                f"Het IBAN op de factuur ({iban_getoond}) wijkt af van het IBAN dat bij deze leverancier bekend "
                f"is ({bekend_getoond}). Dit is een bekende vorm van fraude: controleer het nummer bij de "
                "leverancier voordat u goedkeurt. Goedkeuren zet het nieuwe IBAN bij de leverancier."
            )
        elif isinstance(iban, str) and bekend_iban is None:
            redenen.append("iban_nog_onbekend")
            zinnen.append(
                f"Van deze leverancier is nog geen IBAN bekend. Het IBAN op de factuur ({iban_getoond}) wordt pas "
                "na goedkeuren bij de leverancier gezet."
            )
        elif iban is None and isinstance(bekend_iban, str):
            redenen.append("geen_iban_op_factuur")
            zinnen.append(
                "Op de factuur staat geen (leesbaar) IBAN, terwijl er van deze leverancier een IBAN bekend is; "
                "de agent kan niet vaststellen dat het rekeningnummer klopt."
            )
        factuur_naam = feiten.get("factuur_naam")
        if (
            bekend
            and gevonden_op == "iban"
            and isinstance(factuur_naam, str)
            and _naamsleutel(factuur_naam) != _naamsleutel(str(naam))
        ):
            redenen.append("naam_wijkt_af")
            zinnen.append(
                f"De naam op de factuur ({factuur_naam!r}) is anders dan de naam van de leverancier met dit IBAN "
                f"({naam!r}). Controleer of de factuur wel van deze leverancier komt."
            )
        return redenen, zinnen

    # -- de tools -----------------------------------------------------------------------------------

    async def execute_payables_tool(
        self, tool_name: str, payload: dict[str, object], *, tenant_id: int
    ) -> dict[str, object]:
        """Voer een crediteurentool uit. Geeft altijd een dict; gooit alleen bij onbekend/infra."""
        if tool_name not in self._TOOL_NAMES:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail=f"Payables tool '{tool_name}' is not implemented",
            )
        self._controleer_tenant(tenant_id, tool_name)
        if tool_name == RECORD_TOOL_NAME:
            return await self._record(tenant_id, payload)
        return await self._propose(tenant_id, payload)

    @staticmethod
    def _controleer_tenant(tenant_id: object, tool_name: str = "payables") -> None:
        if not isinstance(tenant_id, int) or isinstance(tenant_id, bool) or tenant_id <= 0:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail="tenant_id must be a positive integer from the execution context",
            )

    async def _record(self, tenant_id: int, payload: dict[str, object]) -> dict[str, object]:
        onbekend = _onbekende_velden(payload, _RECORD_FIELDS)
        if onbekend:
            return {"success": False, "error": f"onbekende velden: {', '.join(onbekend)}"}
        bestand_id = payload.get("bestand_id")
        if not isinstance(bestand_id, str):
            return {"success": False, "error": "bestand_id ontbreekt"}
        oordeel = await self.beoordeel(tenant_id, bestand_id)
        feiten = oordeel["feiten"]
        if oordeel["uitkomst"] != "schoon" or not isinstance(feiten, dict):
            return {
                "success": False,
                "error": "De factuur is niet schoon; de agent legt hem niet zelf vast "
                f"({oordeel['uitkomst']}).",
            }
        return await self._leg_vast(
            tenant_id, bestand_id, feiten, via="agent", na_goedkeuring=False, ticket_ref=None
        )

    async def _propose(self, tenant_id: int, payload: dict[str, object]) -> dict[str, object]:
        """Wat na goedkeuren gebeurt. Het ticket zelf maakt de HITL-poort; deze tak wordt pas daarna bereikt."""
        onbekend = _onbekende_velden(payload, _PROPOSE_FIELDS)
        if onbekend:
            return {"success": False, "error": f"onbekende velden: {', '.join(onbekend)}"}
        bestand_id = payload.get("bestand_id")
        ticket_ref = payload.get("_hitl_ticket_ref")
        if not isinstance(bestand_id, str) or not isinstance(ticket_ref, str):
            return {"success": False, "error": "bestand_id of ticket ontbreekt"}
        oordeel = await self.beoordeel(tenant_id, bestand_id)
        if oordeel["uitkomst"] == "dubbel":
            return {"success": False, "error": _MELDING_DUBBEL}
        redenen, feiten = oordeel["redenen"], oordeel["feiten"]
        ticketfeiten = oordeel.get("ticketfeiten")
        if (
            oordeel["uitkomst"] not in ("schoon", "uitzondering")
            or not isinstance(redenen, list)
            or not isinstance(feiten, dict)
            or not isinstance(ticketfeiten, dict)
        ):
            await self._herstel_na_mislukking(tenant_id, bestand_id, ticket_ref, "niet_meer_leesbaar")
            return {
                "success": False,
                "error": "De factuur kan niet meer worden gelezen; leg hem met de hand vast.",
                "reden_code": "factuur_niet_meer_leesbaar",
            }
        if "ontbrekend_veld" in redenen or "andere_valuta" in redenen:
            return {
                "success": False,
                "error": "Er ontbreken of onzekere gegevens, of de valuta is niet euro: goedkeuren kan niet. "
                "Pas de factuur aan via de bevestigroute.",
                "reden_code": "gegevens_onzeker",
            }
        if any(payload.get(sleutel) != ticketfeiten.get(sleutel) for sleutel in _FEITSLEUTELS):
            await self._herstel_na_mislukking(tenant_id, bestand_id, ticket_ref, "veranderd")
            return {
                "success": False,
                "error": "De factuur of de leverancier is veranderd sinds dit ticket werd gemaakt; "
                "de agent legt niets vast.",
                "reden_code": "factuur_of_leverancier_veranderd",
            }
        stand = _koppeling(_bon_dienst()).lees(tenant_id, bestand_id)
        if (
            not stand
            or stand.get("ticket_ref") != ticket_ref
            or stand.get("payable_id") is not None
        ):
            return {
                "success": False,
                "error": "Deze factuur is al vastgelegd of hoort bij een ander ticket.",
                "reden_code": "factuur_al_vastgelegd",
            }
        return await self._leg_vast(
            tenant_id,
            bestand_id,
            feiten,
            via="agent_na_goedkeuring",
            na_goedkeuring=True,
            ticket_ref=ticket_ref,
        )

    async def _herstel_na_mislukking(
        self, tenant_id: int, bestand_id: str, ticket_ref: str, reden: str
    ) -> None:
        """Een goedgekeurd ticket dat niets meer kan uitvoeren is verbruikt; geef de upload dan vrij voor een nieuwe beoordeling.

        Zonder dit blijft de claim op dat ticket staan en is de factuur een doodlopend spoor (twee facturen van dezelfde NIEUWE
        leverancier: na goedkeuren van de eerste bestaat de leverancier, en het ticket van de tweede klopt niet meer). Alleen de
        claim van DIT ticket wordt vrijgegeven; de volgende beoordeling maakt een vers ticket, of legt hem schoon vast.
        """
        koppeling = _koppeling(_bon_dienst())
        stand = koppeling.lees(tenant_id, bestand_id)
        if not stand or stand.get("ticket_ref") != ticket_ref or stand.get("payable_id") is not None:
            return
        koppeling.geef_vrij(tenant_id, bestand_id)
        await self.schrijf_audit(
            tenant_id,
            "payable_ticket_mislukt",
            f"payable_ticket_mislukt: {reden}",
            {"bestand_id": bestand_id, "ticket_ref": ticket_ref, "reden": reden},
        )

    async def _leg_vast(
        self,
        tenant_id: int,
        bestand_id: str,
        feiten: dict[str, object],
        *,
        via: str,
        na_goedkeuring: bool,
        ticket_ref: str | None,
    ) -> dict[str, object]:
        """Maak (zo nodig) de leverancier aan, zet na goedkeuren een afwijkend IBAN, en leg de factuur vast."""
        naam, nummer = feiten["supplier_name"], feiten["invoice_number"]
        centen, valuta = feiten["amount_cents"], feiten["currency"]
        factuurdatum, vervaldatum = _datum(feiten["invoice_date"]), _datum(feiten["due_date"])
        if not (
            isinstance(naam, str)
            and isinstance(nummer, str)
            and isinstance(centen, int)
            and isinstance(valuta, str)
            and factuurdatum
            and vervaldatum
        ):
            return {"success": False, "error": "Er ontbreken gegevens; de agent legt niets vast."}
        iban = feiten["iban"] if isinstance(feiten["iban"], str) else None
        supplier_id = feiten["supplier_id"]
        # De gebruiker die de verwerking verantwoordt (de uploader) staat in de claim; hij wordt `created_by` en komt in het logboek.
        stand = _koppeling(_bon_dienst()).lees(tenant_id, bestand_id) or {}
        waarde = stand.get("door")
        door = waarde if isinstance(waarde, int) and not isinstance(waarde, bool) else None
        try:
            async with self._tenant_sessie(tenant_id) as session:
                leveranciers = SupplierRepository(session)
                iban_gezet = False
                if isinstance(supplier_id, int):
                    leverancier_id = supplier_id
                    if (
                        na_goedkeuring
                        and iban is not None
                        and feiten["bekend_iban"] != probeer_iban(iban)
                    ):
                        if await leveranciers.update_iban(tenant_id, supplier_id, iban) is None:
                            return {"success": False, "error": "Deze leverancier bestaat niet."}
                        iban_gezet = True
                else:
                    leverancier_id = (
                        await leveranciers.add(tenant_id, NewSupplier(name=naam, iban=iban))
                    ).id
                rij = await PayableRepository(session).add(
                    tenant_id,
                    NewPayable(
                        supplier_id=leverancier_id,
                        invoice_number=nummer,
                        amount_cents=centen,
                        invoice_date=factuurdatum,
                        due_date=vervaldatum,
                        currency=valuta,
                    ),
                    created_by=door,
                )
                await session.commit()
                payable_id = int(rij.id)
                _koppeling(_bon_dienst()).leg_vast(tenant_id, bestand_id, payable_id, door=door)
                details: dict[str, object] = {
                    "payable_id": payable_id,
                    "invoice_number": nummer,
                    "status": "ontvangen",
                    "bestand_id": bestand_id,
                    "via": via,
                    "leverancier_nieuw": not isinstance(supplier_id, int),
                    "iban_gewijzigd": iban_gezet,
                    "initiated_by": door,
                    "ticket_ref": ticket_ref,
                }
                await self._audit(
                    session,
                    tenant_id,
                    "payable_created",
                    f"payable_created: /api/v1/payables/{payable_id}",
                    details,
                    user_id=door,
                )
                if iban_gezet:
                    await self._audit(
                        session,
                        tenant_id,
                        "supplier_iban_changed",
                        "supplier_iban_changed: na een goedgekeurd ticket",
                        {
                            "supplier_id": leverancier_id,
                            "bestand_id": bestand_id,
                            "ticket_ref": ticket_ref,
                            "initiated_by": door,
                            # Gemaskeerd: na een fraude moet te herleiden zijn WAT er veranderde, zonder het nummer in het log.
                            "oud": maskeer_iban(feiten["bekend_iban"]),
                            "nieuw": maskeer_iban(iban),
                        },
                        user_id=door,
                    )
        except IbanAlInGebruik as fout:
            return {"success": False, "error": str(fout), "reden_code": "iban_al_in_gebruik"}
        except ValidatieFout as fout:
            return {"success": False, "error": str(fout)}
        return {"success": True, "payable_id": payable_id, "status": "ontvangen"}

    # -- auditregel (ook voor de skill) -------------------------------------------------------------

    async def schrijf_audit(
        self,
        tenant_id: int,
        event_type: str,
        description: str,
        details: dict[str, object],
    ) -> None:
        """Een auditregel van de crediteurenagent, best-effort in een eigen sessie van DEZE tenant."""
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
        """Best-effort NA de commit van de rij; geen IBAN en geen bedrag in de details."""
        from src.core.utils.best_effort import best_effort

        audit = importlib.import_module("src.core.governance.services.audit_service").AuditService
        async with best_effort(f"auditregel {event_type} voor crediteuren", db_session=session):
            await audit.log_event(
                db=session,
                event_type=event_type,
                severity="low",
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
