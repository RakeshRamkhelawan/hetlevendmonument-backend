"""Vier ogen geldt ook voor tickets uit het ToolBroker-pad (plan nazorg, deel II punt 4).

`POST /api/v1/tools/hitl/request` (`src/core/tool_broker/router.py`) zette `_requested_by` op
het e-mailadres van de aanvrager. `_refuse_self_approval` vergelijkt met het user-id, dus een
zelfgoedkeuring van zo'n ticket werd nooit herkend, ook niet met vier ogen aan.

Deze test maakt het ticket via het ECHTE aanmaakpad en legt het daarna voor aan het echte
goedkeurpad. Alleen de opslag is een dubbel.

Overgang: tickets die nog met een e-mailadres in `_requested_by` staan, worden ook herkend
(`_is_requester`). Dat staat in `TestOudeTicketsMetEenEmailadres`.
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
AANVRAGER = 42
COLLEGA = 43
TOOL = "local__send_email"


def _gebruiker(user_id: int) -> UserResponse:
    return UserResponse(
        id=user_id, email=f"U{user_id}@Klant.nl", tenant_id=TENANT, roles=["admin"]
    )


class _Opslag:
    def __init__(self) -> None:
        self.tickets: dict[str, HITLTicket] = {}

    def repo(self, db: object) -> "_Opslag":
        return self

    async def create(
        self, *, ticket_ref: str, tenant_id: int, tool_name: str, payload: dict[str, object],
        risk_level: str,
    ) -> HITLTicket:
        ticket = HITLTicket(
            ticket_ref=ticket_ref,
            tenant_id=tenant_id,
            status="pending",
            tool_name=tool_name,
            payload=dict(payload),
            risk_level=risk_level,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        )
        ticket.id = len(self.tickets) + 1
        ticket.created_at = datetime.now(timezone.utc)
        ticket.resolved_at = None
        ticket.resolved_by = None
        self.tickets[ticket_ref] = ticket
        return ticket

    async def get(self, ticket_ref: str, tenant_id: int) -> HITLTicket | None:
        ticket = self.tickets.get(ticket_ref)
        return ticket if ticket is not None and ticket.tenant_id == tenant_id else None

    async def approve(self, ticket_ref: str, **kwargs: Any) -> bool:
        self.tickets[ticket_ref].status = "approved"
        return True

    async def reject(self, ticket_ref: str, **kwargs: Any) -> bool:
        self.tickets[ticket_ref].status = "rejected"
        return True


def _app(
    monkeypatch: pytest.MonkeyPatch, opslag: _Opslag, gebruiker: UserResponse, *, vier_ogen: bool
) -> TestClient:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.v1.tool_broker import hitl_router as beslis_module
    from src.core.api.v1.tool_broker.dependencies import get_db as beslis_db
    from src.core.api.v1.tool_broker.dependencies import get_tool_broker_service
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db as aanmaak_db
    from src.core.tool_broker import router as aanmaak_module

    async def _instelling(db: object, *, tenant_id: int, action: str) -> bool:
        return vier_ogen

    monkeypatch.setattr(aanmaak_module, "HITLTicketRepository", opslag.repo)
    monkeypatch.setattr(beslis_module, "HITLTicketRepository", opslag.repo)
    monkeypatch.setattr(beslis_module, "is_four_eyes_required", _instelling)
    monkeypatch.setattr(beslis_module, "notify_ticket_approved", AsyncMock(return_value=None))
    monkeypatch.setattr(beslis_module, "notify_ticket_rejected", AsyncMock(return_value=None))
    monkeypatch.setattr(beslis_module, "_write_audit_entry", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "src.core.tool_broker.hitl_store.get_ticket_async",
        AsyncMock(return_value={"ticket_ref": "x"}),
    )
    broker = AsyncMock()
    broker.execute_tool = AsyncMock(return_value={"success": True})

    app = FastAPI()
    app.include_router(aanmaak_module.router)
    app.include_router(beslis_module.router)
    app.dependency_overrides[aanmaak_db] = lambda: AsyncMock()
    app.dependency_overrides[beslis_db] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: gebruiker
    app.dependency_overrides[get_tool_broker_service] = lambda: broker
    app.dependency_overrides[validate_csrf_token] = lambda: None
    return TestClient(app)


def _vraag_aan(client: TestClient) -> str:
    response = client.post(
        "/v1/tools/hitl/request",
        json={
            "agent_id": "agent-finance-01",
            "tool_name": TOOL,
            "tool_input": {"to": "ops@klant.nl", "subject": "Herinnering"},
            "reason": "Herinnering voor een openstaande factuur",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["ticket_ref"])


def _keur_goed(client: TestClient, ticket_ref: str) -> int:
    return client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": ticket_ref}).status_code


@pytest.mark.unit
class TestEenTicketUitDeToolBroker:
    def test_the_ticket_records_the_user_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        opslag = _Opslag()
        ticket_ref = _vraag_aan(_app(monkeypatch, opslag, _gebruiker(AANVRAGER), vier_ogen=True))
        assert opslag.tickets[ticket_ref].payload["_requested_by"] == str(AANVRAGER)

    def test_the_requester_cannot_approve_it_with_four_eyes_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opslag = _Opslag()
        client = _app(monkeypatch, opslag, _gebruiker(AANVRAGER), vier_ogen=True)
        assert _keur_goed(client, _vraag_aan(client)) == 403

    def test_a_colleague_can_approve_it_with_four_eyes_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opslag = _Opslag()
        ticket_ref = _vraag_aan(_app(monkeypatch, opslag, _gebruiker(AANVRAGER), vier_ogen=True))
        collega = _app(monkeypatch, opslag, _gebruiker(COLLEGA), vier_ogen=True)
        assert _keur_goed(collega, ticket_ref) == 200

    def test_the_requester_can_approve_it_with_four_eyes_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opslag = _Opslag()
        client = _app(monkeypatch, opslag, _gebruiker(AANVRAGER), vier_ogen=False)
        assert _keur_goed(client, _vraag_aan(client)) == 200


@pytest.mark.unit
class TestOudeTicketsMetEenEmailadres:
    """Tickets van voor deze wijziging hebben het e-mailadres in `_requested_by`."""

    def _oud_ticket(self, opslag: _Opslag, email: str) -> str:
        ticket = HITLTicket(
            ticket_ref="hitl_oud0001",
            tenant_id=TENANT,
            status="pending",
            tool_name=TOOL,
            payload={"to": "ops@klant.nl", "_requested_by": email},
            risk_level="HIGH",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        )
        ticket.id = 99
        ticket.created_at = datetime.now(timezone.utc)
        ticket.resolved_at = None
        ticket.resolved_by = None
        opslag.tickets[ticket.ticket_ref] = ticket
        return ticket.ticket_ref

    def test_the_requester_is_recognised_by_email_case_insensitive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opslag = _Opslag()
        ticket_ref = self._oud_ticket(opslag, f"u{AANVRAGER}@klant.nl")
        client = _app(monkeypatch, opslag, _gebruiker(AANVRAGER), vier_ogen=True)
        assert _keur_goed(client, ticket_ref) == 403

    def test_a_colleague_may_still_approve_an_old_ticket(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opslag = _Opslag()
        ticket_ref = self._oud_ticket(opslag, f"u{AANVRAGER}@klant.nl")
        client = _app(monkeypatch, opslag, _gebruiker(COLLEGA), vier_ogen=True)
        assert _keur_goed(client, ticket_ref) == 200
