"""
HITL Notifier Service for real-time WebSocket notifications.

This module provides functions to notify connected clients about
HITL (Human-in-the-Loop) ticket events via WebSocket broadcasts.
"""

from datetime import datetime, timezone
from typing import Any

from loguru import logger

from src.core.tool_broker.hitl_store import get_ticket_async
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.websocket.manager import connection_manager



#: De ENIGE sleutels die over kanaal `hitl:{tenant_id}` mogen (ADR-036 OP-58/OP-66).
#:
#: Kanaal `hitl:{tenant_id}` wordt geserveerd door `/ws/hitl/{tenant_id}`
#: (`api/v1/websocket_hitl.py`) en de enige controle daar is `user.tenant_id != tenant_id` --
#: GEEN rolcheck. Elke ingelogde gebruiker van de tenant kan meelezen. OP-56 zette een
#: beheerdersrol op `/hitl/pending` en `/hitl/audit`; dat beschermt de HTTP-deur, niet dit kanaal.
#:
#: **Waarom een toelaatlijst en geen uitsluitlijst.** De eerste versie sloot een enkele naam uit
#: (`tool_input`). Een blinde review op 2026-08-06 mat wat er dan nog overging: `reason` is
#: `payload["_reason"]`, en dat is `decision.explanation_for_user` -- door het model geschreven
#: proza dat de HIGH-risk handeling beschrijft en in de praktijk de parameters navertelt. Ook
#: `requested_by` ging mee, het e-mailadres van de aanvrager. Dezelfde module gooit `_reason` bij
#: resolutie juist weg omdat het modeltekst is; de uitsluitlijst wist dat niet.
#:
#: Een uitsluitlijst loopt per definitie achter op `hitl_store._to_dict`: elk veld dat daar
#: bijkomt gaat automatisch mee. Een toelaatlijst niet.
#:
#: De client heeft niet meer nodig: dit zegt DAT er iets veranderd is. De inhoud haalt hij op via
#: het endpoint dat wel een rolcheck heeft.
_BROADCASTABLE = ("ticket_ref", "tenant_id", "status", "created_at")


def _broadcast_projection(ticket_data: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Alleen de velden die over een tenantbreed kanaal zonder rolcheck mogen.

    Een projectie hier is duurzamer dan wachten tot de payload bij resolutie wordt opgeruimd: die
    volgorde is timing-afhankelijk en `notify_new_ticket` vuurt juist VOORDAT er iets is opgelost.
    """
    return {key: value for key, value in ticket_data.items() if key in _BROADCASTABLE}


async def broadcast_new_ticket(ticket_ref: str, tenant_id: int) -> int:
    """Meld op kanaal `hitl:{tenant_id}` DAT er een nieuw ticket is; geeft het aantal ontvangers.

    Aangeroepen na de commit door `hitl_repository._meld_na_commit`, voor elk pad dat een ticket
    aanmaakt. Zonder databaseverzoek: de sessie is dan al vastgelegd, en de client heeft niet meer
    nodig dan de ref -- de inhoud haalt hij op via `/hitl/pending`, dat wel een rolcheck heeft.
    Het kanaal komt uit de `tenant_id` van het ticket zelf, nooit uit invoer van buiten.
    """
    message: dict[str, object] = {
        "type": "hitl:new",
        "ticket_ref": ticket_ref,
        "data": {"ticket_ref": ticket_ref, "tenant_id": tenant_id, "status": "pending"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return await connection_manager.broadcast_to_channel(f"hitl:{tenant_id}", dict(message))


async def notify_new_ticket(ticket_ref: str, tenant_id: int, db: AsyncSession) -> bool:
    """
    Notify connected clients about a new HITL ticket.

    Geen productie-aanroeper meer (2026-10-05): elk nieuw ticket wordt gemeld door
    `hitl_repository._meld_na_commit` -> `broadcast_new_ticket`. Roep deze functie niet aan bij
    het aanmaken van een ticket; dan komt de melding dubbel binnen. Bewaakt door
    `tests/architecture/test_elk_nieuw_hitl_ticket_wordt_gemeld.py`.

    Broadcasts a "hitl:new" message to the tenant's HITL channel
    with full ticket data.

    Args:
        ticket_ref: Unique reference for the HITL ticket
        tenant_id: ID of the tenant to broadcast to
        db: Async database session

    Returns:
        True if notification was broadcast successfully, False otherwise
    """
    logger.info(
        "Notifying new HITL ticket: ticket_ref={ticket_ref}, tenant_id={tenant_id}",
        ticket_ref=ticket_ref,
        tenant_id=tenant_id,
    )

    # Retrieve ticket data from store
    ticket_data: dict[str, Any] | None = await get_ticket_async(ticket_ref, tenant_id, db)  # TODO(TYPE): replace Any with concrete type
    if ticket_data is None:
        logger.warning(
            "Cannot notify new ticket: ticket not found: ticket_ref={ticket_ref}",
            ticket_ref=ticket_ref,
        )
        return False

    # Build notification message
    message: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "type": "hitl:new",
        "ticket_ref": ticket_ref,
        "data": _broadcast_projection(ticket_data),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Broadcast to tenant channel
    channel = f"hitl:{tenant_id}"

    try:
        recipient_count = await connection_manager.broadcast_to_channel(channel, message)
        logger.info(
            "Broadcasted hitl:new notification: ticket_ref={ticket_ref}, "
            "channel={channel}, recipients={recipient_count}",
            ticket_ref=ticket_ref,
            channel=channel,
            recipient_count=recipient_count,
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to broadcast hitl:new notification: ticket_ref={ticket_ref}, "
            "channel={channel}, error={error_type}: {error}",
            ticket_ref=ticket_ref,
            channel=channel,
            error_type=type(e).__name__,
            error=e,
            exc_info=True,
        )
        return False


async def notify_ticket_approved(ticket_ref: str, tenant_id: int, approved_by: str, db: AsyncSession) -> bool:
    """
    Notify connected clients about an approved HITL ticket.

    Broadcasts a "hitl:approved" message to the tenant's HITL channel
    with full ticket data and approver information.

    Args:
        ticket_ref: Unique reference for the HITL ticket
        tenant_id: ID of the tenant to broadcast to
        approved_by: Identifier of the user who approved the ticket
        db: Async database session

    Returns:
        True if notification was broadcast successfully, False otherwise
    """
    logger.info(
        "Notifying HITL ticket approval: ticket_ref={ticket_ref}, "
        "tenant_id={tenant_id}, approved_by={approved_by}",
        ticket_ref=ticket_ref,
        tenant_id=tenant_id,
        approved_by=approved_by,
    )

    # Retrieve ticket data from store
    ticket_data: dict[str, Any] | None = await get_ticket_async(ticket_ref, tenant_id, db)  # TODO(TYPE): replace Any with concrete type
    if ticket_data is None:
        logger.warning(
            "Cannot notify ticket approval: ticket not found: ticket_ref={ticket_ref}",
            ticket_ref=ticket_ref,
        )
        return False

    # Build notification message
    message: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "type": "hitl:approved",
        "ticket_ref": ticket_ref,
        "data": _broadcast_projection(ticket_data),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Broadcast to tenant channel
    channel = f"hitl:{tenant_id}"

    try:
        recipient_count = await connection_manager.broadcast_to_channel(channel, message)
        logger.info(
            "Broadcasted hitl:approved notification: ticket_ref={ticket_ref}, "
            "channel={channel}, recipients={recipient_count}",
            ticket_ref=ticket_ref,
            channel=channel,
            recipient_count=recipient_count,
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to broadcast hitl:approved notification: ticket_ref={ticket_ref}, "
            "channel={channel}, error={error_type}: {error}",
            ticket_ref=ticket_ref,
            channel=channel,
            error_type=type(e).__name__,
            error=e,
            exc_info=True,
        )
        return False


async def notify_ticket_rejected(ticket_ref: str, tenant_id: int, rejected_by: str, db: AsyncSession) -> bool:
    """
    Notify connected clients about a rejected HITL ticket.

    Broadcasts a "hitl:rejected" message to the tenant's HITL channel
    with full ticket data and rejector information.

    Args:
        ticket_ref: Unique reference for the HITL ticket
        tenant_id: ID of the tenant to broadcast to
        rejected_by: Identifier of the user who rejected the ticket
        db: Async database session

    Returns:
        True if notification was broadcast successfully, False otherwise
    """
    logger.info(
        "Notifying HITL ticket rejection: ticket_ref={ticket_ref}, "
        "tenant_id={tenant_id}, rejected_by={rejected_by}",
        ticket_ref=ticket_ref,
        tenant_id=tenant_id,
        rejected_by=rejected_by,
    )

    # Retrieve ticket data from store
    ticket_data: dict[str, Any] | None = await get_ticket_async(ticket_ref, tenant_id, db)  # TODO(TYPE): replace Any with concrete type
    if ticket_data is None:
        logger.warning(
            "Cannot notify ticket rejection: ticket not found: ticket_ref={ticket_ref}",
            ticket_ref=ticket_ref,
        )
        return False

    # Build notification message
    message: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "type": "hitl:rejected",
        "ticket_ref": ticket_ref,
        "data": _broadcast_projection(ticket_data),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Broadcast to tenant channel
    channel = f"hitl:{tenant_id}"

    try:
        recipient_count = await connection_manager.broadcast_to_channel(channel, message)
        logger.info(
            "Broadcasted hitl:rejected notification: ticket_ref={ticket_ref}, "
            "channel={channel}, recipients={recipient_count}",
            ticket_ref=ticket_ref,
            channel=channel,
            recipient_count=recipient_count,
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to broadcast hitl:rejected notification: ticket_ref={ticket_ref}, "
            "channel={channel}, error={error_type}: {error}",
            ticket_ref=ticket_ref,
            channel=channel,
            error_type=type(e).__name__,
            error=e,
            exc_info=True,
        )
        return False
