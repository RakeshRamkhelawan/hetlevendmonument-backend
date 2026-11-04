"""De HITL-kaart toont wie het voorstel deed met een naam, niet met een nummer (debiteuren vanzelf afronden, B4).

De acceptant (2026-10-19) zag op de kaart de aanvrager als getal. `_ticket_to_dict` geeft nu ook `requested_by_email`:
het e-mailadres dat de aanroeper heeft opgezocht (net als bij de besluiter). Gemeten:

1. Is het adres bekend, dan staat het in het ticket onder `requested_by_email`; de oude sleutel `requested_by` blijft
   (de zelfgoedkeuring-controle leest hem).
2. Is het niet bekend (gebruiker weg, agent als aanvrager), dan is het veld `None` en wordt er NIETS verzonnen.
3. Alleen een zuiver getal is een gebruikersnummer: een agentnaam, een ontbrekende waarde en een bool zijn dat niet.

Mutatiebewijs: zie de commitboodschap.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from src.core.tool_broker.hitl_store import _aanvrager_id, _ticket_to_dict


def _ticket(payload: dict[str, Any]) -> SimpleNamespace:
    nu = datetime.now(timezone.utc)
    return SimpleNamespace(
        ticket_ref="TOOL-X",
        tenant_id=1,
        status="pending",
        tool_name="send_payment_reminder",
        payload=payload,
        risk_level="HIGH",
        created_at=nu,
        expires_at=nu,
        resolved_at=None,
        resolved_by=None,
        resolution_note=None,
    )


def test_the_requester_email_is_shown_when_it_is_known() -> None:
    resultaat = _ticket_to_dict(_ticket({"_requested_by": "7"}), None, "anna@bedrijf.example")

    assert resultaat["requested_by_email"] == "anna@bedrijf.example"


def test_the_old_requested_by_key_stays_for_the_self_approval_check() -> None:
    resultaat = _ticket_to_dict(_ticket({"_requested_by": "7"}), None, "anna@bedrijf.example")

    assert resultaat["requested_by"] == "7"


def test_an_unknown_requester_gives_none_and_no_invented_name() -> None:
    resultaat = _ticket_to_dict(_ticket({"_requested_by": "7"}), None)

    assert resultaat["requested_by_email"] is None


def test_a_numeric_requester_id_is_recognised() -> None:
    assert _aanvrager_id(_ticket({"_requested_by": "42"})) == 42


def test_an_agent_as_requester_is_not_a_user_id() -> None:
    assert _aanvrager_id(_ticket({"_requested_by": "copilot"})) is None


def test_a_missing_requester_is_not_a_user_id() -> None:
    assert _aanvrager_id(_ticket({})) is None


def test_a_boolean_is_not_a_user_id() -> None:
    assert _aanvrager_id(_ticket({"_requested_by": True})) is None
