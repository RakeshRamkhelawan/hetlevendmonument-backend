"""Debiteurentools voor de debiteurenagent: `list_receivables` en `send_payment_reminder` (dag 2).

Gemodelleerd naar `hr_registry.py`: een tenant-gescoped brug tussen een ToolBroker-payload en de
database. De tenant komt als los argument van de broker (uit de executiecontext), nooit uit de
payload -- zie de toelichting daar (BE-AGT-044, HIGH-4).

**`list_receivables` (MEDIUM) geeft geen naam en geen e-mailadres terug.** Alles wat een tool
teruggeeft gaat de event bus op en wordt door het leersubsysteem bewaard (zie `hr_registry.py`,
OP-27). De agent heeft de naam ook niet nodig: hij kiest een factuur op nummer en id, en de
brief haalt ontvanger en naam zelf uit de database.

**`send_payment_reminder` (HIGH) "verstuurt" door EEN rij in `outgoing_messages` te schrijven**
(besluit 2 van dag 1, geen SMTP). Hij komt pas hier aan nadat de HITL-poort in de broker een
goedgekeurd ticket heeft verzilverd. De payload bevat de VOLLEDIGE brief (ontvanger, onderwerp,
tekst): die stond in het ticket, de goedkeurder heeft hem gelezen, en de goedkeuringsbinding dekt
precies die tekst. De tool rendert de brief opnieuw uit het sjabloon en weigert als er iets
afwijkt -- dan klopt wat de mens zag niet meer met wat er zou vertrekken (bijvoorbeeld een
adres dat sindsdien is gewijzigd).

**Waarom de brief al in het ticket staat.** Scenario 5 eist dat de goedkeurder ziet wat er
gebeurt, aan wie en met welke inhoud. Een ticket met alleen een factuur-id laat hem tekenen voor
een tekst die hij niet heeft gezien. `preview_payment_reminder` levert de parameters; de
debiteurenagent vult ze in voordat de actie langs de Council en de HITL-vloer gaat
(`DunningSkill._prepare_tool_params`).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.payment_reminder_template import (
    REMINDER_KINDS,
    render_payment_reminder,
)

if TYPE_CHECKING:
    from src.core.models.receivable_models import Receivable

logger = logging.getLogger(__name__)

LIST_TOOL_NAME = "list_receivables"
SEND_TOOL_NAME = "send_payment_reminder"

#: Het vocabulaire van de leestool. Elke andere sleutel wordt GEWEIGERD, niet genegeerd: een
#: genegeerd filter levert meer terug dan gevraagd terwijl de aanroeper denkt dat er gefilterd is.
_LIST_FIELDS = frozenset({"status", "limit", "offset"})

#: Het vocabulaire van de schrijftool. Ontvanger, onderwerp en tekst horen erbij: zij zijn wat de
#: mens goedkeurt. Ze komen uit het sjabloon, niet uit het model -- zie de moduledocstring.
_SEND_FIELDS = frozenset(
    {"receivable_id", "kind", "recipient_name", "recipient_email", "subject", "body"}
)

#: Statussen waarop de leestool mag filteren; gelijk aan de CHECK op `receivables.status`.
_STATUSES = ("open", "herinnerd", "geescaleerd", "betaald")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_OFFSET = 100_000


@asynccontextmanager
async def _default_session_factory() -> AsyncGenerator[AsyncSession, None]:
    """Standaard sessie via de centrale DB-manager, net als de HR-registry."""
    from src.core.database.database import db_manager

    async with db_manager.get_session() as session:
        yield session


def _onbekende_velden(payload: dict[str, object], vocabulaire: frozenset[str]) -> list[str]:
    """Sleutels die de tool niet kent; servermetadata (`_`) en broker-sleutels tellen niet mee."""
    from src.core.tool_broker.redaction import BROKER_INJECTED_KEYS

    return sorted(
        k
        for k in payload
        if not k.startswith("_") and k not in vocabulaire and k not in BROKER_INJECTED_KEYS
    )


def _geheel_getal(waarde: object, veld: str, standaard: int, maximum: int) -> int:
    if waarde is None:
        return standaard
    if isinstance(waarde, bool) or not isinstance(waarde, int) or waarde < 0:
        raise ValueError(f"'{veld}' moet een niet-negatief geheel getal zijn")
    return min(waarde, maximum)


class ReceivablesToolRegistry:
    """Voert de debiteurentools uit, altijd binnen EEN tenant."""

    _TOOL_NAMES = frozenset({LIST_TOOL_NAME, SEND_TOOL_NAME})

    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
    ) -> None:
        self._session_factory = session_factory or _default_session_factory

    @classmethod
    def known_tool_names(cls) -> set[str]:
        """De toolnamen die deze registry afhandelt."""
        return set(cls._TOOL_NAMES)

    async def execute_receivables_tool(
        self,
        tool_name: str,
        payload: dict[str, object],
        *,
        tenant_id: int,
    ) -> dict[str, object]:
        """Voer een debiteurentool uit. Geeft altijd een dict; gooit alleen bij onbekend/infra."""
        if tool_name not in self._TOOL_NAMES:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail=f"Receivables tool '{tool_name}' is not implemented",
            )
        if not isinstance(tenant_id, int) or isinstance(tenant_id, bool) or tenant_id <= 0:
            raise ToolExecutionException(
                tool_name=tool_name,
                error_detail="tenant_id must be a positive integer from the execution context",
            )
        if tool_name == LIST_TOOL_NAME:
            return await self._list(tenant_id, payload)
        return await self._send(tenant_id, payload)

    async def preview_payment_reminder(
        self,
        tenant_id: int,
        receivable_id: object,
        kind: object,
        *,
        controleer_dubbel: bool = True,
    ) -> dict[str, object]:
        """De volledige parameters van `send_payment_reminder`, gerenderd uit het sjabloon.

        Geeft `{"success": True, "params": {...}}` of `{"success": False, "error": ...}`. Een
        factuur van een andere tenant bestaat hier niet.

        `controleer_dubbel` (standaard aan): weigert als voor dezelfde factuur en soort al een voorstel op
        goedkeuring wacht of al een brief is klaargezet of verstuurd, en weigert een aanmaning zonder verstuurde
        herinnering (brief 2026-10-24). `_send` zet het uit: het ticket dat daar wordt uitgevoerd is zelf het
        openstaande voorstel, en de controle gebeurt daar opnieuw onder het slot op de factuur.
        """
        if isinstance(receivable_id, bool) or not isinstance(receivable_id, int):
            return {"success": False, "error": "'receivable_id' moet een geheel getal zijn"}
        if kind not in REMINDER_KINDS:
            return {
                "success": False,
                "error": f"'kind' moet een van {', '.join(REMINDER_KINDS)} zijn",
            }
        async with self._tenant_sessie(tenant_id) as session:
            rij = await self._receivable(session, tenant_id, receivable_id)
            if rij is None:
                return {"success": False, "error": "deze factuur bestaat niet binnen deze tenant"}
            if controleer_dubbel:
                reden = await self._weigering_dubbel_of_te_vroeg(
                    session,
                    tenant_id,
                    rij.id,
                    str(kind),
                    tickets_tellen=True,
                    factuur_status=rij.status,
                )
                if reden is not None:
                    return {"success": False, "error": reden}
            brief = render_payment_reminder(
                kind=str(kind),
                customer_name=rij.customer_name,
                customer_email=rij.customer_email,
                invoice_number=rij.invoice_number,
                amount=rij.amount,
                currency=rij.currency,
                due_date=rij.due_date,
            )
        return {
            "success": True,
            "params": {
                "receivable_id": receivable_id,
                "kind": str(kind),
                # Dag 3: de naam erbij, zodat de goedkeurkaart AAN WIE kan tonen. Hij wordt bij
                # uitvoeren net als de tekst vergeleken (zie `_send`).
                "recipient_name": rij.customer_name,
                "recipient_email": brief.recipient,
                "subject": brief.subject,
                "body": brief.body,
            },
        }

    @staticmethod
    async def _weigering_dubbel_of_te_vroeg(
        session: AsyncSession,
        tenant_id: int,
        receivable_id: int,
        kind: str,
        *,
        tickets_tellen: bool,
        factuur_status: str,
    ) -> str | None:
        """De Nederlandse reden waarom deze brief niet mag, of `None`.

        Drie regels, alle drie in de query en per tenant (nooit een bericht of ticket van een andere klant):
        een aanmaning vraagt een VERZONDEN herinnering voor dezelfde factuur (of een dossier dat al `herinnerd` of
        `geescaleerd` is: die status zet alleen de verzendlus nadat een brief is verstuurd); een bericht van dezelfde soort dat al
        `klaar` of `verzonden` is blokkeert een nieuwe; en (alleen bij voorbereiden) een voorstel van dezelfde soort
        dat nog `pending` en niet verlopen is. Een `mislukt` bericht blokkeert niet: dan mag het opnieuw.
        """
        from sqlalchemy import Select, func

        from src.core.models.outgoing_message_models import OutgoingMessage
        from src.core.tool_broker.models import HITLTicket

        def _bericht(soort: str, statussen: tuple[str, ...]) -> Select[tuple[int]]:
            return select(OutgoingMessage.id).where(
                OutgoingMessage.tenant_id == tenant_id,
                OutgoingMessage.receivable_id == receivable_id,
                OutgoingMessage.kind == soort,
                OutgoingMessage.status.in_(statussen),
            )

        if kind == "aanmaning" and factuur_status not in ("herinnerd", "geescaleerd"):
            herinnerd = await session.execute(_bericht("herinnering", ("verzonden",)).limit(1))
            if herinnerd.first() is None:
                return "een aanmaning kan pas na een verstuurde herinnering voor deze factuur"
        bestaand = await session.execute(_bericht(kind, ("klaar", "verzonden")).limit(1))
        if bestaand.first() is not None:
            return f"voor deze factuur is al een {kind} klaargezet of verstuurd"
        if tickets_tellen:
            wachtend = await session.execute(
                select(HITLTicket.id)
                .where(
                    HITLTicket.tenant_id == tenant_id,
                    HITLTicket.tool_name == SEND_TOOL_NAME,
                    HITLTicket.status == "pending",
                    HITLTicket.expires_at > func.now(),
                    HITLTicket.payload["receivable_id"].astext == str(receivable_id),
                    HITLTicket.payload["kind"].astext == kind,
                )
                .limit(1)
            )
            if wachtend.first() is not None:
                return (
                    f"er staat al een {kind} voor deze factuur ter goedkeuring; "
                    "beslis eerst bij Goedkeuringen"
                )
        return None

    @asynccontextmanager
    async def _tenant_sessie(self, tenant_id: int) -> AsyncGenerator[AsyncSession, None]:
        """Een sessie met de tenant-ContextVar gezet, en daarna hersteld.

        Zetten VOOR het openen: het `begin`-event leest deze ContextVar en zet daarmee
        `app.current_tenant` voor RLS (zelfde reden als `hr_registry._schedule_training`).
        """
        from src.core.middleware.tenant_context import get_tenant_id, set_tenant_id

        vorige = get_tenant_id()
        set_tenant_id(tenant_id)
        try:
            async with self._session_factory() as session:
                yield session
        finally:
            set_tenant_id(vorige)

    @staticmethod
    async def _receivable(
        session: AsyncSession, tenant_id: int, receivable_id: int, *, lock: bool = False
    ) -> Receivable | None:
        from src.core.models.receivable_models import Receivable

        statement = select(Receivable).where(
            Receivable.id == receivable_id, Receivable.tenant_id == tenant_id
        )
        if lock:
            # Dag 3: tussen de betaald-controle en het schrijven mag geen andere transactie de
            # rij wijzigen; anders kan een net geboekte betaling alsnog een herinnering krijgen.
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def _list(self, tenant_id: int, payload: dict[str, object]) -> dict[str, object]:
        from src.core.models.receivable_models import Receivable

        onbekend = _onbekende_velden(payload, _LIST_FIELDS)
        if onbekend:
            return {
                "success": False,
                "error": (
                    f"onbekende velden: {', '.join(onbekend)}. Deze tool kent alleen "
                    f"{', '.join(sorted(_LIST_FIELDS))}"
                ),
            }
        status = payload.get("status")
        if status is not None and status not in _STATUSES:
            return {"success": False, "error": f"'status' moet een van {', '.join(_STATUSES)} zijn"}
        try:
            limit = max(1, _geheel_getal(payload.get("limit"), "limit", DEFAULT_LIMIT, MAX_LIMIT))
            offset = _geheel_getal(payload.get("offset"), "offset", 0, MAX_OFFSET)
        except ValueError as exc:
            return {"success": False, "error": f"ongeldige parameter: {exc}"}

        statement = (
            select(Receivable)
            .where(Receivable.tenant_id == tenant_id)
            .order_by(Receivable.due_date, Receivable.id)
            .offset(offset)
            .limit(limit + 1)
        )
        if status is not None:
            statement = statement.where(Receivable.status == status)

        try:
            async with self._tenant_sessie(tenant_id) as session:
                rijen = list((await session.execute(statement)).scalars().all())
        except SQLAlchemyError as exc:
            # Geen exceptietekst terug: die plakt SQL en parameters aan zijn `str()`.
            logger.error(
                "list_receivables mislukt voor tenant %s: %s",
                tenant_id,
                type(exc).__name__,
                exc_info=True,
            )
            return {"success": False, "error": "debiteuren lezen mislukt door een interne fout"}

        zichtbaar = rijen[:limit]
        return {
            "success": True,
            "receivables": [
                {
                    "receivable_id": r.id,
                    "invoice_number": r.invoice_number,
                    "amount": str(r.amount),
                    "currency": r.currency,
                    "due_date": r.due_date.isoformat(),
                    "status": r.status,
                }
                for r in zichtbaar
            ],
            "count": len(zichtbaar),
            "truncated": len(rijen) > limit,
            "applied_limit": limit,
            "applied_offset": offset,
        }

    async def _send(self, tenant_id: int, payload: dict[str, object]) -> dict[str, object]:
        """Schrijf de goedgekeurde brief als EEN uitgaand bericht. Geen inhoud in het antwoord."""
        from src.core.models.outgoing_message_models import OutgoingMessage

        onbekend = _onbekende_velden(payload, _SEND_FIELDS)
        if onbekend:
            return {
                "success": False,
                "error": (
                    f"onbekende velden: {', '.join(onbekend)}. Deze tool kent alleen "
                    f"{', '.join(sorted(_SEND_FIELDS))}"
                ),
            }
        verwacht = await self.preview_payment_reminder(
            tenant_id, payload.get("receivable_id"), payload.get("kind"), controleer_dubbel=False
        )
        if verwacht["success"] is not True:
            return {"success": False, "error": str(verwacht["error"])}
        params = verwacht["params"]
        if not isinstance(params, dict):
            raise ToolExecutionException(
                tool_name=SEND_TOOL_NAME, error_detail="het voorbeeld van de brief is onleesbaar"
            )
        aangeboden = {
            "recipient_name": payload.get("recipient_name"),
            "recipient_email": payload.get("recipient_email"),
            "subject": payload.get("subject"),
            "body": payload.get("body"),
        }
        if any(waarde != params[veld] for veld, waarde in aangeboden.items()):
            # De goedgekeurde tekst klopt niet (meer) met de debiteur. Niet "corrigeren": dan
            # vertrekt er iets dat niemand heeft gezien. Geen waarde in de melding.
            return {
                "success": False,
                "error": (
                    "de brief in het verzoek komt niet overeen met de debiteur; vraag een nieuwe "
                    "goedkeuring aan"
                ),
            }

        ticket_ref = payload.get("_hitl_ticket_ref")
        if not isinstance(ticket_ref, str) or not ticket_ref:
            # Zonder ticketref geen eenmaligheid: UNIQUE telt NULL niet als dubbel. De broker
            # stuurt een HIGH-tool alleen hierheen met een verzilverd ticket; dit is het vangnet.
            return {"success": False, "error": "verzenden kan alleen met een goedgekeurd ticket"}
        receivable_id = params["receivable_id"]
        try:
            async with self._tenant_sessie(tenant_id) as session:
                rij = await self._receivable(
                    session, tenant_id, int(str(receivable_id)), lock=True
                )
                if rij is None:
                    return {"success": False, "error": "deze factuur bestaat niet binnen deze tenant"}
                # Opnieuw renderen uit de VERGRENDELDE rij (code-review dag 3): het voorbeeld
                # hierboven las in een eigen sessie; wijzigt de debiteur daartussen, dan klopt de
                # goedgekeurde brief niet meer en gaat er niets uit.
                vers = render_payment_reminder(
                    kind=str(params["kind"]),
                    customer_name=rij.customer_name,
                    customer_email=rij.customer_email,
                    invoice_number=rij.invoice_number,
                    amount=rij.amount,
                    currency=rij.currency,
                    due_date=rij.due_date,
                )
                if (
                    rij.customer_name != params["recipient_name"]
                    or (vers.recipient, vers.subject, vers.body)
                    != (params["recipient_email"], params["subject"], params["body"])
                ):
                    return {
                        "success": False,
                        "error": (
                            "de debiteur is gewijzigd sinds de goedkeuring; vraag een nieuwe "
                            "goedkeuring aan"
                        ),
                    }
                if rij.status == "betaald":
                    return {
                        "success": False,
                        "error": "deze factuur is al betaald; er gaat geen herinnering uit",
                    }
                # Opnieuw, nu onder het slot op de factuur: tussen goedkeuren en versturen kan een andere
                # goedkeuring voor dezelfde factuur en soort al zijn uitgevoerd. Het ticket zelf telt hier niet.
                reden = await self._weigering_dubbel_of_te_vroeg(
                    session,
                    tenant_id,
                    rij.id,
                    str(params["kind"]),
                    tickets_tellen=False,
                    factuur_status=rij.status,
                )
                if reden is not None:
                    return {"success": False, "error": reden}
                bericht = OutgoingMessage(
                    tenant_id=tenant_id,
                    receivable_id=rij.id,
                    channel="email",
                    kind=str(params["kind"]),
                    recipient=str(params["recipient_email"]),
                    subject=str(params["subject"]),
                    body=str(params["body"]),
                    status="klaar",
                    hitl_ticket_ref=ticket_ref,
                )
                session.add(bericht)
                # De status blijft hier staan: `herinnerd` zet de verzendlus pas als de brief
                # verzonden is (`debiteuren_tasks._verwerk`). Klaarzetten is nog geen herinnering.
                await session.flush()
                bericht_id = bericht.id
                # Expliciet: een schrijftool die op het gedrag van zijn fabriek leunt, schrijft
                # soms niets en meldt succes (zelfde les als `hr_registry._schedule_training`).
                await session.commit()
        except IntegrityError as exc:
            # De unieke `hitl_ticket_ref`: dezelfde goedkeuring levert nooit een tweede bericht.
            logger.warning(
                "send_payment_reminder geweigerd voor tenant %s: %s",
                tenant_id,
                type(exc).__name__,
            )
            raise ToolExecutionException(
                tool_name=SEND_TOOL_NAME,
                error_detail="voor deze goedkeuring bestaat al een bericht",
            ) from exc
        except SQLAlchemyError as exc:
            logger.error(
                "send_payment_reminder mislukt voor tenant %s: %s",
                tenant_id,
                type(exc).__name__,
                exc_info=True,
            )
            raise ToolExecutionException(
                tool_name=SEND_TOOL_NAME, error_detail="het bericht kon niet worden opgeslagen"
            ) from exc

        return {"success": True, "message_id": bericht_id, "kind": params["kind"], "status": "klaar"}
