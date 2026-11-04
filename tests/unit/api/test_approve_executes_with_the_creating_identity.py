"""Verzilveren moet uitvoeren met DEZELFDE identiteit als bij aanmaken getoetst (ADR-036 OP-163).

**Waarom deze test bestaat.** De verplichte blinde eindreview van de Dag 2-fix (2026-08-18)
muteerde `approve_hitl_request()` zo dat `uitvoerende_identiteit` altijd de default (`"copilot"`)
bleef, in plaats van `ticket.payload.get("_executing_identity", ...)` te lezen -- exact het
scenario waarbij de permissiecheck bij AANMAKEN iets anders toetst dan wat er bij UITVOEREN
gebeurt. 352 bestaande tests bleven daarbij groen, want geen van hen zet een ticket met een
NIET-default `_executing_identity` neer en controleert vervolgens met welke `agent_id`
`broker.execute_tool` wordt aangeroepen. Dit bestand is dat vangnet.

Zonder deze test zou een toekomstige refactor van `approve_hitl_request()` de identiteitskoppeling
stilzwijgend kunnen breken: de permissiecheck bij `create_hitl_request` zou een piloot-specifieke
tool goedkeuren, maar de uitvoering zou onder `copilot`'s (kleinere) toolprofiel gebeuren -- precies
het lek dat OP-163 dichtte, nu op het andere eind van de keten.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.auth.auth_service import UserResponse
from src.core.tool_broker.models import HITLTicket

pytestmark = pytest.mark.usefixtures("procesrecht_voor_de_beslisser")

TENANT = 7
TICKET_REF = "hitl-op163-abc123"
APPROVER_ID = 42
REQUESTER_ID = 99  # ongelijk aan APPROVER_ID -- anders slaat _refuse_self_approval toe


def _approver() -> UserResponse:
    return UserResponse(
        id=APPROVER_ID,
        email="beheerder@klant.nl",
        tenant_id=TENANT,
        roles=["admin"],
    )


def _pending_ticket(executing_identity: str | None) -> HITLTicket:
    payload: dict[str, Any] = {
        "employee_id": "e-1",
        "_decision_id": "decision-1",
        "_requested_by": str(REQUESTER_ID),
        "_requested_at": datetime.now(timezone.utc).isoformat(),
    }
    if executing_identity is not None:
        payload["_executing_identity"] = executing_identity

    ticket = HITLTicket(
        ticket_ref=TICKET_REF,
        tenant_id=TENANT,
        status="pending",
        tool_name="query_hr_database",
        payload=payload,
        risk_level="HIGH",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
    )
    ticket.id = 1
    ticket.created_at = datetime.now(timezone.utc)
    ticket.resolved_at = None
    ticket.resolved_by = None
    return ticket


class _FakeRepo:
    """Vervangt `HITLTicketRepository` -- geen echte database nodig voor deze assertie."""

    def __init__(self, ticket: HITLTicket) -> None:
        self._ticket = ticket

    async def get(self, ticket_ref: str, tenant_id: int) -> HITLTicket | None:
        if ticket_ref == self._ticket.ticket_ref and tenant_id == self._ticket.tenant_id:
            return self._ticket
        return None

    async def approve(self, ticket_ref: str, **kwargs: Any) -> bool:
        self._ticket.status = "approved"
        return True


def _client(monkeypatch: pytest.MonkeyPatch, ticket: HITLTicket, broker: AsyncMock) -> TestClient:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.v1.tool_broker import hitl_router as module
    from src.core.api.v1.tool_broker.dependencies import get_db, get_tool_broker_service
    from src.core.auth.dependencies import get_current_user

    monkeypatch.setattr(module, "HITLTicketRepository", lambda db: _FakeRepo(ticket))
    monkeypatch.setattr(module, "notify_ticket_approved", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "src.core.tool_broker.hitl_store.get_ticket_async",
        AsyncMock(return_value={"ticket_ref": ticket.ticket_ref, "status": "approved"}),
    )

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: _approver()
    app.dependency_overrides[get_tool_broker_service] = lambda: broker
    app.dependency_overrides[validate_csrf_token] = lambda: None
    return TestClient(app)


@pytest.mark.unit
class TestApprovalExecutesWithTheCreatingIdentity:
    def test_a_non_default_executing_identity_is_used_at_redemption(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Het ticket droeg `_executing_identity="skillsgaptraining"` -- dat moet uitvoeren."""
        ticket = _pending_ticket(executing_identity="skillsgaptraining")
        broker = AsyncMock()
        broker.execute_tool = AsyncMock(return_value={"success": True})
        client = _client(monkeypatch, ticket, broker)

        response = client.post(
            "/api/v1/tools/hitl/approve",
            json={"ticket_ref": TICKET_REF},
        )

        assert response.status_code == 200, response.text
        broker.execute_tool.assert_awaited_once()
        kwargs = broker.execute_tool.await_args.kwargs
        assert kwargs["agent_id"] == "skillsgaptraining", (
            f"execute_tool is aangeroepen met agent_id={kwargs.get('agent_id')!r}, niet "
            "'skillsgaptraining'. De identiteit die bij het AANMAKEN van het ticket is getoetst "
            "moet ook de identiteit zijn die bij VERZILVEREN uitvoert -- anders keurt de ene "
            "controle iets anders goed dan de andere daadwerkelijk uitvoert (ADR-036 OP-163)."
        )

    def test_a_ticket_without_the_field_falls_back_to_the_default_identity(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Oudere tickets (van voor deze fix) hebben geen `_executing_identity` -- default geldt."""
        ticket = _pending_ticket(executing_identity=None)
        broker = AsyncMock()
        broker.execute_tool = AsyncMock(return_value={"success": True})
        client = _client(monkeypatch, ticket, broker)

        response = client.post(
            "/api/v1/tools/hitl/approve",
            json={"ticket_ref": TICKET_REF},
        )

        assert response.status_code == 200, response.text
        kwargs = broker.execute_tool.await_args.kwargs
        assert kwargs["agent_id"] == "copilot", (
            f"execute_tool is aangeroepen met agent_id={kwargs.get('agent_id')!r} voor een "
            "ticket zonder _executing_identity. Backwards compatibility eist hier de bestaande "
            "default ('copilot')."
        )
