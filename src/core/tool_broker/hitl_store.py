"""HITL ticket store.

DB-backed store replacing the deprecated in-memory dictionary.
All actions delegate to HITLTicketRepository.

Supports four wiring modes:
- repository-bound: a HITLTicketRepository instance is provided (request-scoped)
- session-bound: an AsyncSession is provided
- session-factory: a callable returning an async context manager that yields an
  AsyncSession (used by singletons/agents without a request-scoped session)
- fallback: if nothing is provided, the central db_manager is used per operation
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable, Collection, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Protocol, TYPE_CHECKING

from src.core.tool_broker.hitl_repository import HITLTicketRepository, generate_ticket_ref

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# Async context manager factory for an AsyncSession.
_SessionFactory = Callable[[], AbstractAsyncContextManager["AsyncSession"]]


class HITLStore:
    """
    DB-backed HITL ticket store.
    Replaces the in-memory dict _hitl_tickets (WE-018 fix).
    """

    def __init__(
        self,
        repository: HITLTicketRepository | None = None,
        db_session: "AsyncSession | None" = None,
        session_factory: _SessionFactory | None = None,
    ) -> None:
        self._repository = repository
        self._db_session = db_session
        self._session_factory = session_factory

    @asynccontextmanager
    async def _repository_context(self) -> AsyncGenerator[HITLTicketRepository, None]:
        """Yield a repository, creating a session only when required."""
        if self._repository is not None:
            yield self._repository
            return

        if self._db_session is not None:
            yield HITLTicketRepository(self._db_session)
            return

        if self._session_factory is not None:
            async with self._session_factory() as db:
                yield HITLTicketRepository(db)
            return

        # Fallback: central DB manager creates a session per operation.
        from src.core.database.database import db_manager

        async with db_manager.get_session() as db:
            yield HITLTicketRepository(db)

    async def create_ticket(
        self,
        tool_name: str,
        tenant_id: int,
        user_id: int,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Create a HITL ticket in the database. Returns ticket_ref."""
        ticket_ref = generate_ticket_ref()
        async with self._repository_context() as repo:
            ticket = await repo.create(
                ticket_ref=ticket_ref,
                tenant_id=tenant_id,
                tool_name=tool_name,
                payload=payload,
                risk_level="HIGH",
            )
        return ticket.ticket_ref

    async def get_approval_status(
        self,
        ticket_id: str,
        tenant_id: int | None = None,
    ) -> str | None:
        """Read ticket status from DB. Tenant-scoped if tenant_id is provided."""
        # Note: ticket_id in our codebase refers to ticket_ref (e.g. TOOL-XXXX or hitl_xxxx)
        async with self._repository_context() as repo:
            if tenant_id is None:
                ticket = await repo.get_unchecked(ticket_id)
            else:
                ticket = await repo.get(ticket_id, tenant_id=tenant_id)

        if ticket is None:
            return None
        return ticket.status

    async def redeem_approval(
        self,
        ticket_id: str,
        *,
        tenant_id: int,
        tool_name: str,
        payload: Mapping[str, object],
    ) -> bool:
        """Verzilver een goedkeuring voor precies deze aanroep (ADR-036 OP-63).

        Geeft `True` als er een goedgekeurd, ongebruikt ticket was voor DEZE tool met DEZE
        parameters. Het ticket is daarna verbruikt en niet opnieuw bruikbaar.

        Bewust geen `get_approval_status` gevolgd door een aparte mutatie: dat laat een gat tussen
        de controle en het verbruik, waarin twee gelijktijdige aanroepen allebei `approved` lezen.
        """
        async with self._repository_context() as repo:
            return await repo.redeem(
                ticket_id,
                tenant_id=tenant_id,
                tool_name=tool_name,
                payload=payload,
            )


# ---------------------------------------------------------------------------
# DB-backed async helpers for notification/websocket compatibility
# ---------------------------------------------------------------------------



async def _resolve_user_email(
    db: "AsyncSession", user_id: int, tenant_id: int | None = None
) -> str | None:
    """Het e-mailadres van een gebruiker, of None als hij niet (meer) bestaat.

    Bewust `None` en geen placeholder: dit adres wordt getoond als de mens die een HIGH-risk actie
    heeft goedgekeurd (ADR-036 OP-59). Een verzonnen naam op die plek is een onware bewering in een
    toezichtsrecord.
    """
    from sqlalchemy import select

    from src.core.models.rbac_models import User

    try:
        vraag = select(User.email).where(User.id == user_id)
        if tenant_id is not None:
            # Expliciet tenantfilter naast de hook: een gebruiker van een andere tenant geeft geen adres (Gate 2).
            vraag = vraag.where(User.tenant_id == tenant_id)
        result = await db.execute(vraag)
    except Exception as exc:  # noqa: BLE001 -- gelogd, niet weggeslikt
        logger.error(
            "hitl_store: kon het e-mailadres van gebruiker %s niet oplossen: %s: %s",
            user_id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        return None

    email = result.scalar_one_or_none()
    return email if isinstance(email, str) else None


async def get_ticket_async(
    ticket_ref: str,
    tenant_id: int,
    db: "AsyncSession",
) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
    """Fetch a HITL ticket from the database (tenant-isolated)."""
    repo = HITLTicketRepository(db)
    ticket = await repo.get(ticket_ref=ticket_ref, tenant_id=tenant_id)
    if ticket is None:
        return None

    resolved_email = None
    if ticket.status in ("approved", "rejected") and ticket.resolved_by is not None:
        resolved_email = await _resolve_user_email(db, ticket.resolved_by, tenant_id)
    aanvrager = _aanvrager_id(ticket)
    requester_email = (
        await _resolve_user_email(db, aanvrager, tenant_id) if aanvrager is not None else None
    )
    return _ticket_to_dict(ticket, resolved_email, requester_email)


class _MetPayload(Protocol):
    """Alles wat `_aanvrager_id` van een ticket nodig heeft: de payload."""

    payload: dict[str, object]


def _aanvrager_id(ticket: _MetPayload) -> int | None:
    """Het gebruikersnummer van de aanvrager als `_requested_by` een zuiver getal is, anders `None`.

    `_requested_by` is een string uit JSONB: een gebruikersnummer, of de naam van een agent. Alleen een getal is
    een gebruiker die we kunnen opzoeken; een bool telt niet als getal.
    """
    waarde = ticket.payload.get("_requested_by")
    if isinstance(waarde, bool):
        return None
    if isinstance(waarde, int):
        return waarde
    if isinstance(waarde, str) and waarde.isascii() and waarde.isdigit():
        return int(waarde)
    return None


def _ticket_to_dict(ticket: Any, resolved_email: str | None, requester_email: str | None = None) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """De weergavevorm van een ticket, ZONDER database-toegang.

    Bewust losgemaakt van het ophalen (ADR-036 OP-68). `get_tickets_by_tenant_async` riep voor
    ELK ticket uit zijn eigen lijst opnieuw `get_ticket_async` aan, wat per ticket een tweede
    SELECT op dezelfde rij deed plus een derde voor het e-mailadres. Een enkel verzoek op
    /hitl/audit met de gebruikte limiet van 2000 kwam daarmee op ruim vierduizend opeenvolgende
    queries. De aanroeper bepaalt nu zelf hoe hij aan het e-mailadres komt -- in een lijst met
    EEN query voor alle tickets tegelijk.
    """
    approved_by = None
    approved_at = None
    rejected_by = None
    rejected_at = None

    # De naam van de goedkeurder is PRESENTATIE; `resolved_by` (FK naar users.id) is het bewijs.
    #
    # Hier stond tot 2026-08-05 een terugval op de literal "approver@tenant1.com", in beide takken,
    # plus een kale `except Exception` die elke fout opslokte en diezelfde literal zette
    # (ADR-036 OP-59). Dat veld is wat `/hitl/pending`, `/hitl/audit`, de approve-response en de
    # websocket tonen als de mens die een HIGH-risk actie heeft goedgekeurd -- OP-28 registreert het
    # als de kern van het art.-14-toezicht, en het valt buiten `compute_audit_hash`. Was de
    # gebruiker verwijderd of faalde de query, dan zei het toezichtsrecord dat een verzonnen adres
    # had goedgekeurd.
    #
    # Geen naam als er geen naam is. Een fout in de opzoeking wordt gelogd met `exc_info=True` in
    # plaats van weggeslikt: een lege naam mag, maar een stille fout niet.
    #
    # `consumed` is een goedkeuring waarvan de actie is uitgevoerd (`redeem` zet alleen de
    # status om). Zonder deze tak verloor een uitgevoerde goedkeuring wie en wanneer, en bleef
    # "Approved Today" op /hitl op 0 (acceptant scenario 5, dag 3; gemeten in de
    # approve-response: status consumed, approved_at null).
    if ticket.status in ("approved", "consumed", "rejected") and ticket.resolved_by is not None:
        if ticket.status in ("approved", "consumed"):
            approved_by = resolved_email
            approved_at = ticket.resolved_at.isoformat() if ticket.resolved_at else None
        else:
            rejected_by = resolved_email
            rejected_at = ticket.resolved_at.isoformat() if ticket.resolved_at else None

    # ADR-036 OP-164: NIET `_agent_id` lezen -- `create_hitl_request()` zet die sleutel nooit
    # (de enige schrijver is het niet-gemounte legacy-pad `router.py:466`, dat de waarde
    # bovendien uit een client-gestuurd requestbody-veld haalt). `_executing_identity`
    # (`hitl_repository.py:460`) staat wel op elk live ticket: de identiteit die de
    # permissiecheck bij aanmaken doorstond (OP-163), gezet NA de `**action_params`-spreiding
    # dus nooit overschrijfbaar door een tool-argument of taalmodeloutput (dezelfde
    # veiligheidseis als OP-65 voor `_agent_id`/`_task_id`).
    agent_id = ticket.payload.get("_executing_identity", "unknown")
    reason = ticket.payload.get("_reason", "")
    task_id = ticket.payload.get("_task_id")
    requested_by = ticket.payload.get("_requested_by", "unknown")
    requested_at = ticket.payload.get("_requested_at")

    # Een ticket voorbij zijn termijn telt als verlopen op het moment van LEZEN, ook als de uurlijkse opruimtaak nog niet is gedraaid
    # (crediteuren nazorg, punt 3). Alleen de weergave: de rij verandert niet, en goedkeuren weigert verlopen tickets zelf (`expires_at`).
    status = ticket.status
    if status == "pending" and ticket.expires_at is not None and ticket.expires_at < datetime.now(timezone.utc):
        status = "expired"

    return {
        "ticket_ref": ticket.ticket_ref,
        "tenant_id": ticket.tenant_id,
        "status": status,
        "tool_name": ticket.tool_name,
        # `created_at` en `risk_level` stonden wel in de toelaatlijst van /hitl/audit maar werden
        # nooit opgeleverd (ADR-036 OP-82). Een toezichtsarchief zonder aanmaaktijdstip kan niet
        # zeggen WANNEER er iets is gevraagd, en zonder risiconiveau niet waarom er een mens aan te
        # pas moest komen.
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "risk_level": ticket.risk_level,
        "tool_input": {k: v for k, v in ticket.payload.items() if not k.startswith("_")},
        "agent_id": agent_id,
        "reason": reason,
        "task_id": task_id,
        "requested_by": requested_by,
        # Het adres van de aanvrager, door de aanroeper opgezocht; `None` als hij niet (meer) bestaat of een agent
        # was. Geen verzonnen naam, en de kaal-getal-sleutel hierboven blijft voor de zelfgoedkeuring-controle.
        "requested_by_email": requester_email,
        "requested_at": requested_at,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "rejected_by": rejected_by,
        "rejected_at": rejected_at,
        # Wat de MENS erbij schreef (ADR-036 OP-69). Hier stonden twee `getattr`-constructies naar
        # kolommen die niet bestonden (`notes`, `rejection_reason`), dus dit was altijd None.
        # Onder beide oude namen teruggegeven zodat bestaande clients blijven werken.
        "resolution_note": ticket.resolution_note,
        "notes": ticket.resolution_note if ticket.status == "approved" else None,
        "rejection_reason": ticket.resolution_note if ticket.status == "rejected" else None,
        "expires_at": ticket.expires_at.isoformat() if ticket.expires_at else None,
    }


async def get_tickets_by_tenant_async(
    tenant_id: int,
    db: "AsyncSession",
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    tool_names: Collection[str] | None = None,
    statuses: Collection[str] | None = None,
    nieuwste_besluit_eerst: bool = False,
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """Een pagina tickets van deze tenant, gefilterd en gepagineerd door de database."""
    repo = HITLTicketRepository(db)
    if statuses is None and not nieuwste_besluit_eerst:
        # De bestaande aanroep, ongewijzigd: de wachtrij en de audit kennen de nieuwe parameters niet nodig.
        tickets = await repo.get_by_tenant(
            tenant_id=tenant_id, limit=limit, offset=offset, status=status, tool_names=tool_names
        )
    else:
        tickets = await repo.get_by_tenant(
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
            status=status,
            tool_names=tool_names,
            statuses=statuses,
            nieuwste_besluit_eerst=nieuwste_besluit_eerst,
        )

    # EEN query voor besluiters en aanvragers samen (ADR-036 OP-68: geen query per ticket).
    aanvragers = {t.ticket_ref: _aanvrager_id(t) for t in tickets}
    ids = {t.resolved_by for t in tickets if t.resolved_by}
    ids |= {i for i in aanvragers.values() if i is not None}
    emails = await _resolve_user_emails(db, ids, tenant_id)
    return [
        _ticket_to_dict(
            t,
            emails.get(t.resolved_by) if t.resolved_by is not None else None,
            emails.get(a) if (a := aanvragers[t.ticket_ref]) is not None else None,
        )
        for t in tickets
    ]


async def count_tickets_by_tenant_async(
    tenant_id: int,
    db: "AsyncSession",
    status: str | None = None,
    tool_names: Collection[str] | None = None,
    statuses: Collection[str] | None = None,
) -> int:
    """Het totaal, uit de database -- niet de lengte van een afgetopte pagina."""
    repo = HITLTicketRepository(db)
    if statuses is None:
        return await repo.count_by_tenant(tenant_id=tenant_id, status=status, tool_names=tool_names)
    return await repo.count_by_tenant(
        tenant_id=tenant_id, status=status, tool_names=tool_names, statuses=statuses
    )


async def _resolve_user_emails(
    db: "AsyncSession", user_ids: set[int], tenant_id: int | None = None
) -> dict[int, str]:
    """De e-mailadressen van meerdere gebruikers in EEN query (ADR-036 OP-68).

    Ontbrekende gebruikers komen simpelweg niet in de uitkomst voor; de aanroeper krijgt dan
    `None`, net als bij `_resolve_user_email`. Geen verzonnen naam -- zie OP-59.
    """
    if not user_ids:
        return {}

    from sqlalchemy import select

    from src.core.models.rbac_models import User

    try:
        vraag = select(User.id, User.email).where(User.id.in_(user_ids))
        if tenant_id is not None:
            vraag = vraag.where(User.tenant_id == tenant_id)
        result = await db.execute(vraag)
    except Exception as exc:  # noqa: BLE001 -- gelogd, niet weggeslikt
        logger.error(
            "hitl_store: kon e-mailadressen niet oplossen voor %d gebruikers: %s: %s",
            len(user_ids),
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        return {}

    return {row[0]: row[1] for row in result.all() if isinstance(row[1], str)}
