"""ADR-036 OP-164: `/hitl/pending` toonde voor ELK ticket "agent_id": "unknown".

Root cause (geverifieerd, niet aangenomen): `hitl_store.py::_ticket_to_dict()` las
`ticket.payload.get("_agent_id", "unknown")`, maar `HITLTicketRepository.create_hitl_request()`
zet die sleutel nooit -- de enige schrijver was het bevestigd niet-gemounte legacy-pad
`src/core/tool_broker/router.py:466`, dat de waarde bovendien rechtstreeks uit een
HTTP-requestbody-veld haalde (client-gestuurd, dus geen betrouwbaar herkomstbewijs).

Wat WEL op elk live ticket staat: `_executing_identity` (`hitl_repository.py:460`), de
identiteit die de permissiecheck bij aanmaken doorstond (OP-163) -- voor ALS-skills en de
OP-24-Council-consultatie de echte `agent_id`, anders de bewuste default "copilot". Dit veld
wordt in het payload-dict NA de `**action_params`-spreiding gezet (`hitl_repository.py:502-508`),
dus het kan -- anders dan `_agent_id` ooit kon -- nooit door een tool-argument of taalmodeloutput
worden overschreven. Dat is dezelfde veiligheidseis die
`tests/integration/test_hitl_integration.py::test_approving_keeps_the_decision` (OP-65) bewaakt
voor `_agent_id`/`_task_id`.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from src.core.tool_broker.hitl_store import _ticket_to_dict


def _ticket(payload: dict[str, Any]) -> SimpleNamespace:
    nu = datetime.now(timezone.utc)
    return SimpleNamespace(
        ticket_ref="TOOL-X",
        tenant_id=1,
        status="pending",
        tool_name="create_task",
        payload=payload,
        risk_level="HIGH",
        created_at=nu,
        expires_at=nu,
        resolved_at=None,
        resolved_by=None,
        resolution_note=None,
    )


def test_a_real_executing_identity_is_shown_as_the_agent_id() -> None:
    """De kern van OP-164: een echte, server-bepaalde identiteit moet zichtbaar zijn."""
    ticket = _ticket({"_executing_identity": "skillsgaptraining"})

    result = _ticket_to_dict(ticket, None)

    assert result["agent_id"] == "skillsgaptraining"


def test_a_ticket_without_any_executing_identity_falls_back_to_unknown() -> None:
    """Defensief gedrag voor historische/legacy tickets zonder dit veld blijft behouden."""
    ticket = _ticket({})

    result = _ticket_to_dict(ticket, None)

    assert result["agent_id"] == "unknown"


def test_a_stray_agent_id_key_in_the_payload_is_never_used() -> None:
    """De oude, niet-vertrouwde sleutel `_agent_id` mag NOOIT als terugval dienen.

    Zou dit een stille terugval zijn, dan komt een taalmodel-/tool-argument dat toevallig
    `_agent_id` heet weer terug als "bewijs" van herkomst -- exact de OP-65-fout.
    """
    ticket = _ticket({"_agent_id": "hallucinated-agent"})

    result = _ticket_to_dict(ticket, None)

    assert result["agent_id"] == "unknown"
