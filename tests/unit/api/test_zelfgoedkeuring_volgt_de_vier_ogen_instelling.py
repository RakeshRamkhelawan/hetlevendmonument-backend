"""Zelf goedkeuren volgt de vier-ogen-instelling van de tenant (ADR-039, besluit Rakesh 2026-10-04).

Tot deze wijziging weigerde `_refuse_self_approval` elke zelfgoedkeuring. Het besluit in ADR-039:
mens-in-de-lus blijft altijd aan, maar wie de agent startte mag zijn eigen verzoek beslissen --
tenzij de tenant vier ogen heeft aangezet voor die actie, of de aanvrager een agent is
(Agent2Agent). Wat blijft: de tenantgrens en het recht om te beslissen.

De repository is een dubbel (geen database nodig voor de beslisregel); de echte database-lezing
van de instelling staat in `tests/integration/scenarios/test_scenario_5_betalingsherinnering.py`.
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
ANDERE_TENANT = 8
AANVRAGER = 42
COLLEGA = 43
TICKET_REF = "hitl_vierogen0001"
TOOL = "send_payment_reminder"


def _gebruiker(user_id: int, tenant_id: int = TENANT) -> UserResponse:
    return UserResponse(
        id=user_id, email=f"u{user_id}@klant.nl", tenant_id=tenant_id, roles=["admin"]
    )


def _ticket(*, requester_kind: str | None = "user") -> HITLTicket:
    payload: dict[str, Any] = {
        "receivable_id": 1,
        "_decision_id": "besluit-1",
        "_requested_by": str(AANVRAGER),
        "_requested_at": datetime.now(timezone.utc).isoformat(),
        "_executing_identity": "dunning",
    }
    if requester_kind is not None:
        payload["_requester_kind"] = requester_kind
    ticket = HITLTicket(
        ticket_ref=TICKET_REF,
        tenant_id=TENANT,
        status="pending",
        tool_name=TOOL,
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
    def __init__(self, ticket: HITLTicket) -> None:
        self._ticket = ticket

    async def get(self, ticket_ref: str, tenant_id: int) -> HITLTicket | None:
        if ticket_ref == self._ticket.ticket_ref and tenant_id == self._ticket.tenant_id:
            return self._ticket
        return None

    async def approve(self, ticket_ref: str, **kwargs: Any) -> bool:
        self._ticket.status = "approved"
        return True

    async def reject(self, ticket_ref: str, **kwargs: Any) -> bool:
        self._ticket.status = "rejected"
        return True


def _client(
    monkeypatch: pytest.MonkeyPatch,
    ticket: HITLTicket,
    *,
    beslisser: UserResponse,
    vier_ogen: bool,
) -> TestClient:
    from src.core.api.auth.dependencies import validate_csrf_token
    from src.core.api.v1.tool_broker import hitl_router as module
    from src.core.api.v1.tool_broker.dependencies import get_db, get_tool_broker_service
    from src.core.auth.dependencies import get_current_user

    async def _instelling(db: object, *, tenant_id: int, action: str) -> bool:
        return vier_ogen

    monkeypatch.setattr(module, "HITLTicketRepository", lambda db: _FakeRepo(ticket))
    # `raising=False`: voor de wijziging bestaat deze naam nog niet, en dan moet de test rood
    # zijn op het GEDRAG (403 waar 200 hoort), niet op een AttributeError van de opzet.
    monkeypatch.setattr(module, "is_four_eyes_required", _instelling, raising=False)
    monkeypatch.setattr(module, "notify_ticket_approved", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "notify_ticket_rejected", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "src.core.tool_broker.hitl_store.get_ticket_async",
        AsyncMock(return_value={"ticket_ref": ticket.ticket_ref}),
    )
    broker = AsyncMock()
    broker.execute_tool = AsyncMock(return_value={"success": True})

    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: beslisser
    app.dependency_overrides[get_tool_broker_service] = lambda: broker
    app.dependency_overrides[validate_csrf_token] = lambda: None
    return TestClient(app)


def _keur_goed(client: TestClient) -> int:
    return client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": TICKET_REF}).status_code


def _keur_af(client: TestClient) -> int:
    return client.post(
        "/api/v1/tools/hitl/reject",
        json={"ticket_ref": TICKET_REF, "reason": "deze klant heeft al betaald"},
    ).status_code


@pytest.mark.unit
class TestVierOgenUit:
    def test_the_requester_may_approve_their_own_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _client(monkeypatch, _ticket(), beslisser=_gebruiker(AANVRAGER), vier_ogen=False)
        assert _keur_goed(client) == 200

    def test_the_requester_may_reject_their_own_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _client(monkeypatch, _ticket(), beslisser=_gebruiker(AANVRAGER), vier_ogen=False)
        assert _keur_af(client) == 200


@pytest.mark.unit
class TestVierOgenAan:
    def test_the_requester_may_not_approve_their_own_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _client(monkeypatch, _ticket(), beslisser=_gebruiker(AANVRAGER), vier_ogen=True)
        assert _keur_goed(client) == 403

    def test_the_requester_may_not_reject_their_own_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _client(monkeypatch, _ticket(), beslisser=_gebruiker(AANVRAGER), vier_ogen=True)
        assert _keur_af(client) == 403

    def test_a_colleague_may_approve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Zonder deze helft is 'niemand mag' een geldige oplossing voor de twee hierboven."""
        client = _client(monkeypatch, _ticket(), beslisser=_gebruiker(COLLEGA), vier_ogen=True)
        assert _keur_goed(client) == 200


@pytest.mark.unit
class TestAgentTotAgent:
    def test_an_agent_request_is_never_approved_by_its_requester(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _client(
            monkeypatch,
            _ticket(requester_kind="agent"),
            beslisser=_gebruiker(AANVRAGER),
            vier_ogen=False,
        )
        assert _keur_goed(client) == 403

    def test_an_agent_request_may_be_approved_by_a_human_colleague(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _client(
            monkeypatch,
            _ticket(requester_kind="agent"),
            beslisser=_gebruiker(COLLEGA),
            vier_ogen=False,
        )
        assert _keur_goed(client) == 200


@pytest.mark.unit
class TestTenantgrens:
    def test_another_tenant_never_sees_the_ticket_even_with_four_eyes_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _client(
            monkeypatch,
            _ticket(),
            beslisser=_gebruiker(COLLEGA, tenant_id=ANDERE_TENANT),
            vier_ogen=False,
        )
        assert _keur_goed(client) == 404


@pytest.mark.unit
class TestDeInstellingLezen:
    """De zuivere regel achter `is_four_eyes_required`: welke vorm telt als AAN."""

    def test_a_tenant_without_settings_has_four_eyes_off(self) -> None:
        from src.core.governance.four_eyes import four_eyes_from_settings

        assert four_eyes_from_settings(None, TOOL) is False

    def test_a_listed_action_has_four_eyes_on(self) -> None:
        from src.core.governance.four_eyes import four_eyes_from_settings

        assert four_eyes_from_settings({"four_eyes_actions": [TOOL]}, TOOL) is True

    def test_an_unlisted_action_has_four_eyes_off(self) -> None:
        from src.core.governance.four_eyes import four_eyes_from_settings

        assert four_eyes_from_settings({"four_eyes_actions": ["delete_task"]}, TOOL) is False

    def test_a_malformed_list_turns_four_eyes_on_for_safety(self) -> None:
        """Een instelling die er IS maar onleesbaar is, valt dicht: iemand bedoelde iets."""
        from src.core.governance.four_eyes import four_eyes_from_settings

        assert four_eyes_from_settings({"four_eyes_actions": TOOL}, TOOL) is True


@pytest.mark.unit
class TestDeAanvragersoortIsServerGezet:
    async def test_a_model_written_requester_kind_is_overwritten(self) -> None:
        from src.core.tool_broker.hitl_repository import HITLTicketRepository

        repo = HITLTicketRepository(AsyncMock())
        repo.create = AsyncMock()  # type: ignore[method-assign]
        await repo.create_hitl_request(
            tenant_id=TENANT,
            user_id=AANVRAGER,
            decision_id="d",
            reason="r",
            action_type="delete_task",
            action_params={"task_id": "1", "_requester_kind": "user"},
            requester_kind="agent",
        )
        aanroep = repo.create.await_args
        assert aanroep is not None
        assert aanroep.kwargs["payload"]["_requester_kind"] == "agent"

    async def test_the_default_requester_kind_is_user(self) -> None:
        from src.core.tool_broker.hitl_repository import HITLTicketRepository

        repo = HITLTicketRepository(AsyncMock())
        repo.create = AsyncMock()  # type: ignore[method-assign]
        await repo.create_hitl_request(
            tenant_id=TENANT,
            user_id=AANVRAGER,
            decision_id="d",
            reason="r",
            action_type="delete_task",
            action_params={"task_id": "1", "_requester_kind": "agent"},
        )
        aanroep = repo.create.await_args
        assert aanroep is not None
        assert aanroep.kwargs["payload"]["_requester_kind"] == "user"
