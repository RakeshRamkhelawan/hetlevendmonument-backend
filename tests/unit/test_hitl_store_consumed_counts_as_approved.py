"""Acceptant scenario 5 (dag 3): "Approved Today" bleef 0 na een goedkeuring.

Gemeten bron: de approve-response van de tweede beheerder
(`scratch/acceptant-scenario5-dag3/07f-tweede-beheerder-approve.network-response`) gaf
`"status": "consumed"` met `"approved_at": null`. Goedkeuren voert de actie meteen uit en
`HITLTicketRepository.redeem` zet de status daarna op `consumed` (hitl_repository.py, de
update met `.values(status="consumed")`), met `resolved_at`/`resolved_by` ongemoeid.
`_ticket_to_dict` vulde `approved_*` alleen bij status `approved`, dus een uitgevoerde
goedkeuring verloor wie en wanneer.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from src.core.tool_broker.hitl_store import _ticket_to_dict

_BESLOTEN = datetime(2026, 10, 5, 4, 56, 40, tzinfo=timezone.utc)


def _consumed_ticket() -> SimpleNamespace:
    return SimpleNamespace(
        ticket_ref="hitl_b3cd4137c2414ae4",
        tenant_id=1,
        status="consumed",
        tool_name="send_payment_reminder",
        payload={},
        risk_level="HIGH",
        created_at=_BESLOTEN,
        expires_at=_BESLOTEN,
        resolved_at=_BESLOTEN,
        resolved_by=102,
        resolution_note=None,
    )


def test_a_consumed_ticket_keeps_its_approval_time() -> None:
    """Een uitgevoerde goedkeuring houdt haar tijdstip."""
    result = _ticket_to_dict(_consumed_ticket(), "tweede@example.com")

    assert result["approved_at"] == _BESLOTEN.isoformat()


def test_a_consumed_ticket_keeps_its_approver() -> None:
    """Een uitgevoerde goedkeuring houdt haar goedkeurder."""
    result = _ticket_to_dict(_consumed_ticket(), "tweede@example.com")

    assert result["approved_by"] == "tweede@example.com"
