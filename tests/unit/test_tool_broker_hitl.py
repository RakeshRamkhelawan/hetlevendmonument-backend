"""Unit tests for HITL (Human-in-the-Loop) API endpoints and service gate.

Covers:
- POST /v1/tools/hitl/request  - happy + unhappy paths
- POST /api/v1/tools/hitl/approve  - happy + unhappy paths
- POST /api/v1/tools/hitl/reject   - happy + unhappy paths
- GET /api/v1/tools/hitl/pending   - pagination, tenant isolation
- GET /api/v1/tools/hitl/audit     - pagination, tenant isolation
- ToolBrokerService HITL gate  - blocks/passes correctly (ADR-015)

ADR-015: Agent Tool Execution Safety Allowlist and Audit
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Deze tests voeren echt een tool uit en hebben dus een tenant in de executiecontext
# nodig (ADR-036 OP-27: de pseudonimiseringsscope van de payload hangt eraan).
from tests.fixtures.tool_execution_tenant import tool_execution_tenant  # noqa: F401
from fastapi import FastAPI
from src.core.exceptions import register_exception_handlers
from fastapi.testclient import TestClient

from src.core.auth.auth_service import UserResponse
from src.core.api.auth.dependencies import validate_csrf_token
from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db
from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.risk_classifier import ToolRiskClassifier, ToolRiskLevel
from src.core.api.v1.tool_broker.hitl_router import router as hitl_router
from src.core.tool_broker.router import router
from src.core.tool_broker.service import ToolBrokerService

pytestmark = pytest.mark.usefixtures("procesrecht_voor_de_beslisser")


@pytest.fixture(autouse=True)
def _allow_all_tools():
    """Bypass ToolPermissionManager for service unit tests -- permission logic tested separately."""
    with patch(
        "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
        return_value=True,
    ):
        yield


# ---------------------------------------------------------------------------
# Mock Database Storage for Unit Tests
# ---------------------------------------------------------------------------

_mock_db_tickets: dict[str, Any] = {}

#: Wat de nep-broker bij het goedkeuren te verwerken kreeg (ADR-036 OP-89).
_UITGEVOERD: list[dict[str, Any]] = []


class MockHITLTicket:
    def __init__(self, **kwargs: Any) -> None:
        self.id = kwargs.get("id", 1)
        self.ticket_ref = kwargs.get("ticket_ref")
        self.tenant_id = kwargs.get("tenant_id")
        self.status = kwargs.get("status", "pending")
        self.tool_name = kwargs.get("tool_name")
        self.payload = kwargs.get("payload") or {}
        self.risk_level = kwargs.get("risk_level", "HIGH")
        self.created_at = kwargs.get("created_at") or datetime.now(timezone.utc)
        # NU + de SLA, niet NU: de echte `create` doet `now + timedelta(hours=_SLA_HOURS)`.
        # Met NU is elk ticket bij aanmaak al verlopen, en dan meet een goedkeurtest niet het
        # gedrag maar de klok (ADR-036 OP-64).
        self.expires_at = kwargs.get("expires_at") or (
            datetime.now(timezone.utc) + timedelta(hours=4)
        )
        self.resolved_at = kwargs.get("resolved_at")
        self.resolved_by = kwargs.get("resolved_by")
        self.resolution_note = kwargs.get("resolution_note")


class MockHITLTicketRepository:
    def __init__(self, db: Any = None) -> None:
        self._db = db

    async def create(
        self,
        *,
        ticket_ref: str,
        tenant_id: int,
        tool_name: str,
        payload: dict[str, object],
        risk_level: str,
    ) -> MockHITLTicket:
        ticket = MockHITLTicket(
            id=len(_mock_db_tickets) + 1,
            ticket_ref=ticket_ref,
            tenant_id=tenant_id,
            tool_name=tool_name,
            payload=payload,
            risk_level=risk_level,
        )
        _mock_db_tickets[ticket_ref] = ticket
        return ticket

    async def get(self, ticket_ref: str, tenant_id: int) -> MockHITLTicket | None:
        ticket = _mock_db_tickets.get(ticket_ref)
        if ticket and ticket.tenant_id == tenant_id:
            return ticket
        return None

    async def get_unchecked(self, ticket_ref: str) -> MockHITLTicket | None:
        return _mock_db_tickets.get(ticket_ref)

    async def get_by_tenant(
        self,
        tenant_id: int,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        tool_names: list[str] | None = None,
    ) -> list[MockHITLTicket]:
        """Spiegelt de echte query sinds ADR-036 OP-68: filteren, sorteren en pagineren gebeurt
        HIER, niet bij de aanroeper. De router haalde eerder 2000 rijen op om er in Python op te
        filteren; daardoor gaf `offset` boven 2000 stil een lege pagina en was `total` afgetopt.
        """
        tickets = [t for t in _mock_db_tickets.values() if t.tenant_id == tenant_id]
        if status is not None:
            tickets = [t for t in tickets if t.status == status]
        if tool_names is not None:
            tickets = [t for t in tickets if t.tool_name in tool_names]
        tickets.sort(key=lambda t: t.created_at)
        return tickets[offset : offset + limit]

    async def count_by_tenant(
        self, tenant_id: int, status: str | None = None, tool_names: list[str] | None = None
    ) -> int:
        tickets = [t for t in _mock_db_tickets.values() if t.tenant_id == tenant_id]
        if status is not None:
            tickets = [t for t in tickets if t.status == status]
        if tool_names is not None:
            tickets = [t for t in tickets if t.tool_name in tool_names]
        return len(tickets)

    async def approve(
        self,
        ticket_ref: str,
        tenant_id: int,
        user_id: int,
        redacted_payload: dict[str, object] | None = None,
        binding: str | None = None,
        note: str | None = None,
    ) -> bool:
        # `redacted_payload` volgt de echte signatuur sinds ADR-036 OP-47: de router
        # berekent de digest van wat wordt weggegooid en geeft die mee. De mock bewaart
        # geen payload, dus hij negeert hem -- maar de parameter MOET bestaan, anders
        # toetsen deze tests een andere signatuur dan die in productie draait.
        #
        # `binding` volgt de echte signatuur sinds OP-63 en wordt hier WEL bewaard: zonder
        # die waarde kan `redeem` hieronder niet vaststellen dat de aangeboden aanroep
        # dezelfde is als de goedgekeurde, en dan toetst de gate-test niets.

        now = datetime.now(timezone.utc)
        ticket = _mock_db_tickets.get(ticket_ref)
        if (
            ticket
            and ticket.tenant_id == tenant_id
            and ticket.status == "pending"
            # De echte `approve` filtert sinds OP-64 op `expires_at`: de SLA van 4 uur werd
            # uitsluitend gehandhaafd door een opruimactor die nergens draait.
            and ticket.expires_at > now
        ):
            ticket.status = "approved"
            ticket.resolved_by = user_id
            ticket.resolved_at = now
            ticket.resolution_note = note
            if binding is not None:
                ticket.payload = {**ticket.payload, "_approval_binding": binding}
            return True
        return False

    async def redeem(
        self,
        ticket_ref: str,
        *,
        tenant_id: int,
        tool_name: str,
        payload: dict[str, object],
    ) -> bool:
        """Spiegelt `HITLTicketRepository.redeem` (ADR-036 OP-63).

        Vier voorwaarden, allemaal noodzakelijk: het ticket bestaat binnen deze tenant, staat op
        `approved`, is voor DEZE tool, en de parameters komen overeen met wat er is goedgekeurd.
        Daarna is het verbruikt. Een mock die minder eist dan de productiecode maakt de gate-test
        waardeloos -- precies waarom deze tests eerder een onbegrensde volmacht groen lieten.
        """
        from src.core.tool_broker.redaction import approval_binding

        ticket = _mock_db_tickets.get(ticket_ref)
        if ticket is None or ticket.tenant_id != tenant_id:
            return False
        if ticket.status != "approved" or ticket.tool_name != tool_name:
            return False
        expected = ticket.payload.get("_approval_binding")
        if expected != approval_binding(tool_name, payload, tenant_id=tenant_id):
            return False
        ticket.status = "consumed"
        return True

    async def reject(
        self,
        ticket_ref: str,
        tenant_id: int,
        user_id: int,
        redacted_payload: dict[str, object] | None = None,
        note: str | None = None,
    ) -> bool:
        # `redacted_payload` volgt de echte signatuur sinds ADR-036 OP-47: de router
        # berekent de digest van wat wordt weggegooid en geeft die mee. De mock bewaart
        # geen payload, dus hij negeert hem -- maar de parameter MOET bestaan, anders
        # toetsen deze tests een andere signatuur dan die in productie draait.

        ticket = _mock_db_tickets.get(ticket_ref)
        if ticket and ticket.tenant_id == tenant_id and ticket.status == "pending":
            ticket.status = "rejected"
            ticket.resolved_by = user_id
            ticket.resolved_at = datetime.now(timezone.utc)
            ticket.resolution_note = note
            return True
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(tenant_id: int = 1, email: str = "user@test.com") -> UserResponse:
    return UserResponse(id=1, email=email, tenant_id=tenant_id, roles=[], scopes=[])


def _make_app(user: UserResponse) -> FastAPI:
    """Build a minimal FastAPI app with HITL router and overrides."""
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    # De vier HITL-endpoints staan sinds 2026-08-05 in een eigen router (ADR-036 OP-37).
    # Beide mounten zodat deze tests dezelfde eigenschappen blijven toetsen; de paden zijn
    # ongewijzigd (`/api/v1/tools/hitl/...`).
    app.include_router(hitl_router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: AsyncMock()  # Overwrite DB session
    # De CSRF-controle (ADR-036 OP-72) leunt op Redis en op een header die deze tests niet zetten.
    # Hier overschreven zodat de tests hun EIGEN eigenschap blijven toetsen; DAT de controle
    # bestaat wordt bewezen door `TestTheStateChangingRoutesRequireACsrfToken`, die hem juist
    # NIET overschrijft.
    app.dependency_overrides[validate_csrf_token] = lambda: None
    # Sinds ADR-036 OP-89 VOERT goedkeuren de actie uit. Zonder deze override draait de echte
    # broker op een mock-sessie en meldt de auditregel een uitvoeringsfout -- dan toetsen deze
    # tests iets anders dan hun eigen eigenschap. De nep-broker legt vast WAARMEE hij is
    # aangeroepen, zodat `TestApprovingActuallyExecutes` daar op kan oordelen.
    from src.core.api.v1.tool_broker.dependencies import get_tool_broker_service

    _UITGEVOERD.clear()

    class _NepBroker:
        async def execute_tool(self, *, tool_name, payload, agent_id, context):
            _UITGEVOERD.append(
                {
                    "tool_name": tool_name,
                    "payload": dict(payload),
                    "agent_id": agent_id,
                    "context": dict(context),
                }
            )
            return {"status": "ok"}

    app.dependency_overrides[get_tool_broker_service] = lambda: _NepBroker()
    return app


def _seed_ticket(
    ticket_ref: str,
    tenant_id: int,
    status: str = "pending",
    tool_name: str = "local__send_email",
) -> None:
    """Zet een kant-en-klaar ticket rechtstreeks in de mock-opslag.

    Een ticket met status `approved` krijgt de binding die de echte `approve()` erin schrijft
    (ADR-036 OP-63). Zonder die waarde modelleert de seeder een toestand die in productie niet kan
    bestaan -- een goedkeuring zonder vastgelegde tool en parameters -- en dan toetst de gate-test
    iets anders dan wat er draait.
    """
    from src.core.tool_broker.redaction import approval_binding

    payload: dict[str, object] = {}
    if status == "approved":
        payload["_approval_binding"] = approval_binding(tool_name, {}, tenant_id=tenant_id)

    ticket = MockHITLTicket(
        id=len(_mock_db_tickets) + 1,
        ticket_ref=ticket_ref,
        tenant_id=tenant_id,
        status=status,
        tool_name=tool_name,
        payload=payload,
        risk_level="HIGH",
    )
    _mock_db_tickets[ticket_ref] = ticket


def _make_broker_service() -> ToolBrokerService:
    """ToolBrokerService with mocked clients and real risk classifier."""
    serena = AsyncMock()
    seq = AsyncMock()
    return ToolBrokerService(
        serena_client=serena,
        seq_thinking_client=seq,
        enable_resilience=False,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _vier_ogen_aan(monkeypatch) -> None:
    """Zet de vier-ogen-instelling AAN voor elke actie (ADR-039), zonder database."""

    async def _aan(db, *, tenant_id, action):
        return True

    monkeypatch.setattr(
        "src.core.api.v1.tool_broker.hitl_router.is_four_eyes_required", _aan
    )


@pytest.fixture(autouse=True)
def _mock_repo(monkeypatch):
    """Mock the repository to use in-memory mock storage."""
    _mock_db_tickets.clear()
    # Sinds 2026-08-05 staan de vier HITL-handlers in `hitl_router.py` (ADR-036 OP-37) en die heeft
    # zijn EIGEN module-level import van `HITLTicketRepository`. Alleen `router` patchen laat de
    # handlers de echte repository gebruiken; met een `AsyncMock()`-db levert dat een coroutine op
    # waar een ticket wordt verwacht (`'coroutine' object has no attribute 'status'`). Beide
    # patchen, want `/hitl/request` staat nog in het oude bestand.
    monkeypatch.setattr(
        "src.core.api.v1.tool_broker.hitl_router.HITLTicketRepository",
        MockHITLTicketRepository,
    )
    monkeypatch.setattr(
        "src.core.tool_broker.router.HITLTicketRepository",
        MockHITLTicketRepository,
    )
    monkeypatch.setattr(
        "src.core.tool_broker.hitl_store.HITLTicketRepository",
        MockHITLTicketRepository,
    )
    yield
    _mock_db_tickets.clear()


@pytest.fixture
def client():
    """TestClient authenticated as tenant 1."""
    user = _make_user(tenant_id=1, email="approver@tenant1.com")
    return TestClient(_make_app(user))


@pytest.fixture
def client_tenant2():
    """TestClient authenticated as tenant 2."""
    user = _make_user(tenant_id=2, email="approver@tenant2.com")
    return TestClient(_make_app(user))


def _make_admin(tenant_id: int = 1, email: str = "admin@test.com") -> UserResponse:
    """Een tenant-beheerder.

    Nodig sinds ADR-036 OP-31: `/hitl/audit` is een permanent archief van
    goedkeuringsverzoeken en vereist een adminrol. `/hitl/pending` -- het
    goedkeuringsoppervlak -- niet, want dat is waar AI Act art. 14 over gaat.
    """
    return UserResponse(id=1, email=email, tenant_id=tenant_id, roles=["admin"], scopes=[])


@pytest.fixture
def admin_client():
    """TestClient authenticated as a tenant admin of tenant 1."""
    return TestClient(_make_app(_make_admin(tenant_id=1, email="admin@tenant1.com")))


@pytest.fixture
def admin_client_tenant2():
    """TestClient authenticated as a tenant admin of tenant 2."""
    return TestClient(_make_app(_make_admin(tenant_id=2, email="admin@tenant2.com")))


# ---------------------------------------------------------------------------
# POST /v1/tools/hitl/request - happy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestCreateHITLRequestHappy:
    def test_high_risk_tool_returns_201_with_ticket_ref(self, client, monkeypatch):
        monkeypatch.setattr(
            "src.core.tool_broker.router._risk_classifier",
            _make_classifier(ToolRiskLevel.HIGH),
        )
        resp = client.post(
            "/v1/tools/hitl/request",
            json={
                "agent_id": "agent-finance-01",
                "tool_name": "local__send_email",
                "tool_input": {"to": "ops@tenant1.com", "subject": "Opruimrapport"},
                "reason": "Scheduled cleanup task - removing stale temp files",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert "ticket_ref" in body["data"]
        assert body["data"]["status"] == "pending"

    def test_ticket_stored_with_correct_tenant_and_email(self, client, monkeypatch):
        monkeypatch.setattr(
            "src.core.tool_broker.router._risk_classifier",
            _make_classifier(ToolRiskLevel.HIGH),
        )
        resp = client.post(
            "/v1/tools/hitl/request",
            json={
                "agent_id": "agent-x",
                "tool_name": "local__send_email",
                "reason": "Testing ticket metadata correctness now",
            },
        )
        assert resp.status_code == 201
        ticket_ref = resp.json()["data"]["ticket_ref"]
        stored = _mock_db_tickets[ticket_ref]
        assert stored.tenant_id == 1
        # Het user-id, niet het e-mailadres: vier ogen vergelijkt op id (plan nazorg deel II).
        assert stored.payload["_requested_by"] == "1"
        assert stored.status == "pending"

    def test_ticket_ref_format_starts_with_TOOL_prefix(self, client, monkeypatch):
        monkeypatch.setattr(
            "src.core.tool_broker.router._risk_classifier",
            _make_classifier(ToolRiskLevel.HIGH),
        )
        resp = client.post(
            "/v1/tools/hitl/request",
            json={
                "agent_id": "agent-check",
                "tool_name": "local__send_email",
                "reason": "Sending compliance digest to finance team",
            },
        )
        ticket_ref = resp.json()["data"]["ticket_ref"]
        assert ticket_ref.startswith("TOOL-") or ticket_ref.startswith("hitl_")


# ---------------------------------------------------------------------------
# POST /v1/tools/hitl/request - unhappy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestCreateHITLRequestUnhappy:
    def test_low_risk_tool_returns_400(self, client, monkeypatch):
        monkeypatch.setattr(
            "src.core.tool_broker.router._risk_classifier",
            _make_classifier(ToolRiskLevel.LOW),
        )
        resp = client.post(
            "/v1/tools/hitl/request",
            json={
                "agent_id": "agent-x",
                "tool_name": "local__read_file",
                "reason": "Read-only access to config file for audit",
            },
        )
        assert resp.status_code == 400
        assert "low" in resp.json()["detail"].lower()

    def test_medium_risk_tool_returns_400(self, client, monkeypatch):
        monkeypatch.setattr(
            "src.core.tool_broker.router._risk_classifier",
            _make_classifier(ToolRiskLevel.MEDIUM),
        )
        resp = client.post(
            "/v1/tools/hitl/request",
            json={
                "agent_id": "agent-x",
                "tool_name": "local__write_file",
                "reason": "Writing monthly report to shared folder",
            },
        )
        assert resp.status_code == 400
        assert "medium" in resp.json()["detail"].lower()

    def test_missing_reason_returns_422(self, client, monkeypatch):
        monkeypatch.setattr(
            "src.core.tool_broker.router._risk_classifier",
            _make_classifier(ToolRiskLevel.HIGH),
        )
        resp = client.post(
            "/v1/tools/hitl/request",
            json={"agent_id": "agent-x", "tool_name": "local__send_email"},
        )
        assert resp.status_code == 422

    def test_reason_too_short_returns_422(self, client, monkeypatch):
        monkeypatch.setattr(
            "src.core.tool_broker.router._risk_classifier",
            _make_classifier(ToolRiskLevel.HIGH),
        )
        resp = client.post(
            "/v1/tools/hitl/request",
            json={"agent_id": "agent-x", "tool_name": "local__send_email", "reason": "short"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /v1/tools/hitl/approve - happy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestApproveHITLHappy:
    def test_pending_ticket_approves_successfully(self, admin_client):
        _seed_ticket("TOOL-AABB1122", tenant_id=1)
        resp = admin_client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-AABB1122"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "approved"

    def test_approval_sets_approved_by_from_server_side(self, admin_client):
        _seed_ticket("TOOL-AABB1122", tenant_id=1)
        resp = admin_client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-AABB1122"})
        # De goedkeurder komt van de SERVER, niet van de client. Deze test verwachtte tot
        # 2026-08-05 de literal "approver@tenant1.com" -- een placeholder die de productiecode
        # invulde als de gebruiker niet gevonden werd (ADR-036 OP-59). Daarmee legde hij een
        # VERZONNEN naam vast als het art.-14-bewijs. In deze mock bestaat gebruiker 1 niet in
        # de database, dus het juiste antwoord is: geen naam.
        approved_by = resp.json()["data"]["approved_by"]
        assert approved_by is None, (
            f"approved_by is {approved_by!r} terwijl de gebruiker niet in de database staat."
        )
        assert approved_by != "approver@tenant1.com", (
            "de verzonnen placeholder is terug -- OP-59 is teruggedraaid"
        )

    def test_approval_with_optional_notes_stores_notes(self, client):
        # In DB model notes is stored inside HITLTicket table notes field (resolved in approve logic)
        # Note: notes are returned in dict if schema maps it
        pass

    def test_approval_sets_approved_at_timestamp(self, admin_client):
        _seed_ticket("TOOL-TIMECHK", tenant_id=1)
        resp = admin_client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-TIMECHK"})
        assert resp.json()["data"]["approved_at"] is not None

    def test_approved_ticket_reflected_in_store(self, admin_client):
        _seed_ticket("TOOL-STORECHECK", tenant_id=1)
        admin_client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-STORECHECK"})
        assert _mock_db_tickets["TOOL-STORECHECK"].status == "approved"


# ---------------------------------------------------------------------------
# POST /v1/tools/hitl/approve - unhappy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestApproveHITLUnhappy:
    def test_nonexistent_ticket_returns_404(self, admin_client):
        resp = admin_client.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-DOESNTEXIST"}
        )
        assert resp.status_code == 404

    def test_cross_tenant_ticket_returns_404(self, admin_client, admin_client_tenant2):
        _seed_ticket("TOOL-TENANT1", tenant_id=1)
        # Een BEHEERDER van tenant 2 -- de eigenschap is tenant-isolatie, niet autorisatie.
        # Met een gewone tenant-2-gebruiker antwoordt de route sinds OP-56 eerst 403 en
        # toetst deze test de isolatie niet meer.
        resp = admin_client_tenant2.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-TENANT1"}
        )
        assert resp.status_code == 404

    def test_already_approved_returns_400(self, admin_client):
        _seed_ticket("TOOL-ALREADYOK", tenant_id=1, status="approved")
        resp = admin_client.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-ALREADYOK"}
        )
        assert resp.status_code == 400
        assert "approved" in resp.json()["detail"].lower()

    def test_already_rejected_returns_400(self, admin_client):
        _seed_ticket("TOOL-REJECTED1", tenant_id=1, status="rejected")
        resp = admin_client.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-REJECTED1"}
        )
        assert resp.status_code == 400
        assert "rejected" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /v1/tools/hitl/reject - happy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestRejectHITLHappy:
    def test_pending_ticket_rejects_successfully(self, admin_client):
        _seed_ticket("TOOL-REJHAPPY", tenant_id=1)
        resp = admin_client.post(
            "/api/v1/tools/hitl/reject",
            json={
                "ticket_ref": "TOOL-REJHAPPY",
                "reason": "Command targets production; use the safe cleanup script instead",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "rejected"

    def test_rejection_sets_rejected_by_from_server_side(self, admin_client):
        _seed_ticket("TOOL-REJBY", tenant_id=1)
        resp = admin_client.post(
            "/api/v1/tools/hitl/reject",
            json={
                "ticket_ref": "TOOL-REJBY",
                "reason": "Insufficient justification for production access",
            },
        )
        # Zie de toelichting bij test_approval_sets_approved_by_from_server_side (OP-59).
        rejected_by = resp.json()["data"]["rejected_by"]
        assert rejected_by is None, (
            f"rejected_by is {rejected_by!r} terwijl de gebruiker niet in de database staat."
        )
        assert rejected_by != "approver@tenant1.com", (
            "de verzonnen placeholder is terug -- OP-59 is teruggedraaid"
        )


# ---------------------------------------------------------------------------
# POST /v1/tools/hitl/reject - unhappy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestRejectHITLUnhappy:
    def test_nonexistent_ticket_returns_404(self, admin_client):
        resp = admin_client.post(
            "/api/v1/tools/hitl/reject",
            json={"ticket_ref": "TOOL-GHOST", "reason": "No such ticket anywhere in system"},
        )
        assert resp.status_code == 404

    def test_cross_tenant_ticket_returns_404(self, admin_client, admin_client_tenant2):
        _seed_ticket("TOOL-XTENANTREJ", tenant_id=1)
        resp = admin_client_tenant2.post(
            "/api/v1/tools/hitl/reject",
            json={"ticket_ref": "TOOL-XTENANTREJ", "reason": "Cross-tenant attempt rejection"},
        )
        assert resp.status_code == 404

    def test_already_approved_ticket_returns_400(self, admin_client):
        _seed_ticket("TOOL-REJAPPR", tenant_id=1, status="approved")
        resp = admin_client.post(
            "/api/v1/tools/hitl/reject",
            json={"ticket_ref": "TOOL-REJAPPR", "reason": "Should have been rejected earlier"},
        )
        assert resp.status_code == 400

    def test_already_rejected_ticket_returns_400(self, admin_client):
        _seed_ticket("TOOL-REJREJ", tenant_id=1, status="rejected")
        resp = admin_client.post(
            "/api/v1/tools/hitl/reject",
            json={"ticket_ref": "TOOL-REJREJ", "reason": "Duplicate rejection attempt"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /v1/tools/hitl/pending - happy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestListPendingHITLHappy:
    def test_returns_only_pending_tickets_for_tenant(self, admin_client):
        _seed_ticket("TOOL-PEND1", tenant_id=1, status="pending")
        _seed_ticket("TOOL-PEND2", tenant_id=1, status="approved")
        _seed_ticket("TOOL-PEND3", tenant_id=2, status="pending")  # other tenant
        resp = admin_client.get("/api/v1/tools/hitl/pending")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]) == 1
        assert body["data"][0]["ticket_ref"] == "TOOL-PEND1"

    def test_total_reflects_unpaginated_count(self, admin_client):
        for i in range(5):
            _seed_ticket(f"TOOL-PEND-{i:02d}", tenant_id=1, status="pending")
        resp = admin_client.get("/api/v1/tools/hitl/pending?limit=2&offset=0")
        body = resp.json()
        assert body["total"] == 5
        assert len(body["data"]) == 2

    def test_offset_paginates_results(self, admin_client):
        for i in range(3):
            _seed_ticket(f"TOOL-PAGE-{i:02d}", tenant_id=1)
        resp_p1 = admin_client.get("/api/v1/tools/hitl/pending?limit=2&offset=0")
        resp_p2 = admin_client.get("/api/v1/tools/hitl/pending?limit=2&offset=2")
        refs_p1 = {t["ticket_ref"] for t in resp_p1.json()["data"]}
        refs_p2 = {t["ticket_ref"] for t in resp_p2.json()["data"]}
        assert refs_p1.isdisjoint(refs_p2)

    def test_empty_store_returns_empty_list(self, admin_client):
        resp = admin_client.get("/api/v1/tools/hitl/pending")
        body = resp.json()
        assert body["data"] == []
        assert body["total"] == 0

    def test_response_contains_pagination_fields(self, admin_client):
        resp = admin_client.get("/api/v1/tools/hitl/pending?limit=10&offset=0")
        body = resp.json()
        assert "limit" in body
        assert "offset" in body
        assert "total" in body
        assert body["limit"] == 10
        assert body["offset"] == 0


# ---------------------------------------------------------------------------
# GET /v1/tools/hitl/audit - happy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestListHITLAuditHappy:
    """Het audit-archief. ADMIN-only sinds ADR-036 OP-31 -- vandaar `admin_client`."""

    def test_returns_all_statuses_for_tenant(self, admin_client):
        _seed_ticket("TOOL-AUD1", tenant_id=1, status="pending")
        _seed_ticket("TOOL-AUD2", tenant_id=1, status="approved")
        _seed_ticket("TOOL-AUD3", tenant_id=1, status="rejected")
        _seed_ticket("TOOL-AUD4", tenant_id=2, status="pending")  # excluded
        resp = admin_client.get("/api/v1/tools/hitl/audit")
        body = resp.json()
        assert body["total"] == 3
        statuses = {t["status"] for t in body["data"]}
        assert statuses == {"pending", "approved", "rejected"}

    def test_cross_tenant_tickets_not_included(self, admin_client, admin_client_tenant2):
        _seed_ticket("TOOL-T1", tenant_id=1, status="approved")
        _seed_ticket("TOOL-T2", tenant_id=2, status="approved")
        resp1 = admin_client.get("/api/v1/tools/hitl/audit")
        resp2 = admin_client_tenant2.get("/api/v1/tools/hitl/audit")
        assert resp1.json()["total"] == 1
        assert resp2.json()["total"] == 1
        assert resp1.json()["data"][0]["ticket_ref"] == "TOOL-T1"
        assert resp2.json()["data"][0]["ticket_ref"] == "TOOL-T2"


@pytest.mark.unit
@pytest.mark.als
class TestListHITLAuditIsNotAGeneralReadSurface:
    """ADR-036 OP-31: het permanente archief was voor elke ingelogde gebruiker leesbaar.

    Het endpoint had als enige dependency `get_current_user` en projecteerde het ONBEWERKTE
    `tool_input` plus `requested_by`. Voor de tools die een ticket krijgen -- HIGH-risk, dus
    `local__send_email` -- is dat de klaartekst van de aanroep. Daarmee was
    de pseudonimisering uit OP-27 langs de voordeur omzeilbaar: wat in de ADR-019 auditketen een
    digest is, stond hier in het klare.
    """

    def test_a_normal_tenant_user_is_refused(self, client):
        """Zonder adminrol geen archief. Deze test is ROOD op commit 69af87d0."""
        _seed_ticket("TOOL-SECRET", tenant_id=1, status="approved")

        resp = client.get("/api/v1/tools/hitl/audit")

        assert resp.status_code == 403, (
            "Een gewone gebruiker van de tenant krijgt het volledige HITL-archief. Dat is geen "
            "goedkeuringshandeling maar een permanent leesrecht op wie wat heeft aangevraagd."
        )

    def test_the_archive_does_not_return_the_raw_tool_input(self, admin_client):
        """Ook voor een beheerder: het archief laat zien DAT er iets is gevraagd, niet WAT."""
        _seed_ticket("TOOL-SECRET2", tenant_id=1, status="approved")

        body = admin_client.get("/api/v1/tools/hitl/audit").json()

        assert body["data"], "geen tickets teruggekregen -- dan toetst deze test niets"
        assert all("tool_input" not in ticket for ticket in body["data"]), (
            "Het archief bevat `tool_input`. Dezelfde gegevens zijn in de auditketen "
            "gepseudonimiseerd (OP-27); hier in het klare uitleveren maakt dat zinloos."
        )

    # `test_the_approval_surface_still_shows_the_values_to_a_normal_user` stond hier tot
    # 2026-08-05. Die test eiste dat een GEWONE gebruiker `/hitl/pending` kan lezen, met het
    # argument dat "adminrol op alles" het menselijk toezicht een formaliteit maakt.
    #
    # Dat argument is geldig en is NIET weggegooid -- het staat nu in de docstring van
    # `TestTheApprovalSurfaceIsNotSelfApproving` en als vervolg bij OP-40 (een echte
    # goedkeurdersrol). Maar de test legde daarmee ook vast dat elke ingelogde gebruiker het
    # ONBEWERKTE `tool_input` van elk openstaand ticket kon lezen EN elk ticket kon goedkeuren.
    # Dat maakt de HITL-gate zelf-goedkeurend, en dat is erger dan een beheerdersbottleneck.
    #
    # De art.-14-eigenschap die deze test borgde is overgenomen door
    # `TestTheApprovalSurfaceIsNotSelfApproving::test_an_approver_still_sees_the_real_values`, en
    # die is strikt sterker: hij toetst niet alleen de statuscode maar ook DAT `tool_input` in het
    # antwoord staat. Er is dus geen dekking verloren.


# ---------------------------------------------------------------------------
# Service gate tests (ToolBrokerService.execute_tool HITL gate, ADR-015)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestServiceHITLGate:
    @pytest.mark.asyncio
    async def test_high_risk_tool_without_ticket_raises_exception(self):
        service = _make_broker_service()
        # Mock database session to pass router level, but on service execution we test gate block
        with pytest.raises(ToolExecutionException) as exc_info:
            await service.execute_tool("local__send_email", payload={})
        assert (
            "human approval" in str(exc_info.value.detail).lower()
            or "high risk" in str(exc_info.value.detail).lower()
        )

    @pytest.mark.asyncio
    async def test_high_risk_tool_with_pending_ticket_raises_exception(self):
        _seed_ticket("TOOL-PENDSVC", tenant_id=1, status="pending")
        service = _make_broker_service()
        # Set database mock on service
        from src.core.tool_broker.hitl_store import HITLStore

        service.hitl_store = HITLStore(MockHITLTicketRepository())

        with pytest.raises(ToolExecutionException) as exc_info:
            await service.execute_tool(
                "local__send_email",
                payload={"_hitl_ticket_ref": "TOOL-PENDSVC"},
            )
        detail = str(exc_info.value.detail).lower()
        assert "human approval" in detail or "high risk" in detail

    @pytest.mark.asyncio
    async def test_high_risk_tool_with_wrong_tenant_ticket_raises_exception(self):
        _seed_ticket("TOOL-WRONGTENANT", tenant_id=2, status="approved")
        service = _make_broker_service()
        from src.core.tool_broker.hitl_store import HITLStore

        service.hitl_store = HITLStore(MockHITLTicketRepository())

        with pytest.raises(ToolExecutionException) as exc_info:
            await service.execute_tool(
                "local__send_email",
                payload={"_hitl_ticket_ref": "TOOL-WRONGTENANT", "tenant_id": 1},
            )
        detail = str(exc_info.value.detail).lower()
        assert "human approval" in detail or "high risk" in detail

    @pytest.mark.asyncio
    async def test_high_risk_tool_with_approved_ticket_passes_gate(self):
        _seed_ticket("TOOL-APPROVEDSVC", tenant_id=1, status="approved")
        service = _make_broker_service()
        from src.core.tool_broker.hitl_store import HITLStore

        service.hitl_store = HITLStore(MockHITLTicketRepository())

        with pytest.raises(ToolExecutionException) as exc_info:
            await service.execute_tool(
                "local__send_email",
                payload={"_hitl_ticket_ref": "TOOL-APPROVEDSVC"},
            )
        assert "local tool registry" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_low_risk_tool_bypasses_hitl_gate(self):
        service = _make_broker_service()
        service.serena_client.call = AsyncMock(return_value={"results": []})
        result = await service.execute_tool("serena__search", payload={"query": "test"})
        assert result == {"results": []}

    @pytest.mark.asyncio
    async def test_medium_risk_tool_bypasses_hitl_gate(self):
        service = _make_broker_service()
        service.serena_client.call = AsyncMock(return_value={"written": True})
        result = await service.execute_tool("serena__write_document", payload={"content": "data"})
        assert result == {"written": True}


# ---------------------------------------------------------------------------
# User behavioral test
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestHITLUserBehavioralFlow:
    def test_full_approval_flow_allows_tool_execution(self, admin_client, monkeypatch):
        monkeypatch.setattr(
            "src.core.tool_broker.router._risk_classifier",
            _make_classifier(ToolRiskLevel.HIGH),
        )
        create_resp = admin_client.post(
            "/v1/tools/hitl/request",
            json={
                "agent_id": "agent-finance",
                "tool_name": "local__send_email",
                "reason": "Removing stale temp files as part of scheduled cleanup task",
            },
        )
        assert create_resp.status_code == 201
        ticket_ref = create_resp.json()["data"]["ticket_ref"]

        approve_resp = admin_client.post(
            "/api/v1/tools/hitl/approve",
            json={"ticket_ref": ticket_ref, "notes": "Safe operation confirmed by team lead"},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["data"]["status"] == "approved"

        stored = _mock_db_tickets[ticket_ref]
        assert stored.status == "approved"
        assert stored.resolved_by == 1  # current_user.id is overridden as 1 in _make_user

        service = _make_broker_service()
        from src.core.tool_broker.hitl_store import HITLStore

        service.hitl_store = HITLStore(MockHITLTicketRepository())

        async def _run():
            with pytest.raises(ToolExecutionException) as exc_info:
                await service.execute_tool(
                    "local__send_email",
                    payload={"_hitl_ticket_ref": ticket_ref},
                )
            assert "local tool registry" in str(exc_info.value.detail).lower()

        asyncio.get_event_loop().run_until_complete(_run())

    def test_rejected_ticket_does_not_pass_gate(self, client, monkeypatch):
        monkeypatch.setattr(
            "src.core.tool_broker.router._risk_classifier",
            _make_classifier(ToolRiskLevel.HIGH),
        )
        create_resp = client.post(
            "/v1/tools/hitl/request",
            json={
                "agent_id": "agent-rogue",
                "tool_name": "local__send_email",
                "reason": "Sending quarterly digest to all customers in system",
            },
        )
        ticket_ref = create_resp.json()["data"]["ticket_ref"]

        client.post(
            "/api/v1/tools/hitl/reject",
            json={
                "ticket_ref": ticket_ref,
                "reason": "Not authorized to email all customers without legal review",
            },
        )

        service = _make_broker_service()
        from src.core.tool_broker.hitl_store import HITLStore

        service.hitl_store = HITLStore(MockHITLTicketRepository())

        async def _run():
            with pytest.raises(ToolExecutionException) as exc_info:
                await service.execute_tool(
                    "local__send_email",
                    payload={"_hitl_ticket_ref": ticket_ref},
                )
            detail = str(exc_info.value.detail).lower()
            assert "human approval" in detail or "high risk" in detail

        asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Helper: construct a mock risk classifier returning a fixed level
# ---------------------------------------------------------------------------


def _make_classifier(level: ToolRiskLevel) -> ToolRiskClassifier:
    """Return a ToolRiskClassifier whose classify() always returns `level`."""
    mock = MagicMock(spec=ToolRiskClassifier)
    mock.classify.return_value = level
    return mock


@pytest.mark.unit
@pytest.mark.als
class TestTheApprovalSurfaceIsNotSelfApproving:
    """ADR-036 OP-56 (ronde 7): `/hitl/approve` en `/hitl/reject` hadden geen rolcheck.

    **Waarom dit erger is dan een leesrecht.** OP-31 sloot het archief af omdat elke ingelogde
    gebruiker kon LEZEN wie wat had aangevraagd. Hier gaat het om HANDELEN: beide endpoints hadden
    als enige dependency `get_current_user`, dus elke gebruiker met een geldig tenant-token kon elk
    openstaand ticket goedkeuren. Daarmee is de HITL-gate uit ADR-015 zelf-goedkeurend -- de
    tool-broker weigert een HIGH-risk actie zonder goedgekeurd ticket, en de aanvrager keurt zijn
    eigen ticket goed. Dan is de poort een formaliteit in plaats van toezicht.

    Vandaag is dit LATENT: `src/core/tool_broker/router.py` heeft nul importeurs (OP-37) en de app
    serveert alleen `/api/v1/gatekeeper/hitl/{approve,reject}`. Maar niets verhindert dat deze
    router gemount wordt, en de vorige ronde heeft aangetoond dat "latent" geen borging is.

    **De afweging die hieronder verschuift, expliciet.** De vorige test op dit oppervlak
    (`test_the_approval_surface_still_shows_the_values_to_a_normal_user`) beargumenteerde dat
    "adminrol op alles" het menselijk toezicht een formaliteit maakt, omdat er dan te weinig mensen
    kunnen goedkeuren. Dat argument is geldig, maar het alternatief is erger: een poort die de
    aanvrager zelf kan openen beschermt niets. De juiste oplossing is een echte GOEDKEURDERSROL, en
    die bestaat vandaag niet -- er zijn zeven admin-checks in drie onverenigbare vocabulaires
    (OP-40). Tot die er is, is de beheerdersrol de enige beschikbare grens die niet zelf-goedkeurend
    is. Dat staat als vervolg geregistreerd bij OP-40, niet als afgedaan.

    De art.-14-eigenschap blijft geborgd, maar op de goedkeurder in plaats van op iedereen:
    `test_an_approver_still_sees_the_real_values` hieronder.
    """

    def test_a_normal_user_cannot_approve(self, client, procesrecht_poort):
        procesrecht_poort(set())
        _seed_ticket("TOOL-SELFAPPROVE", tenant_id=1, status="pending")

        resp = client.post(
            "/api/v1/tools/hitl/approve",
            json={"ticket_ref": "TOOL-SELFAPPROVE"},
        )

        assert resp.status_code == 403, (
            f"Een gewone tenantgebruiker mag goedkeuren (status {resp.status_code}). Daarmee kan de "
            "aanvrager zijn eigen HIGH-risk actie vrijgeven en is de HITL-gate uit ADR-015 leeg."
        )

    def test_a_normal_user_cannot_reject(self, client, procesrecht_poort):
        procesrecht_poort(set())
        _seed_ticket("TOOL-SELFREJECT", tenant_id=1, status="pending")

        resp = client.post(
            "/api/v1/tools/hitl/reject",
            # `reason` eist min_length=10; met een kortere waarde antwoordt FastAPI 422 op de
            # schemavalidatie en toetst deze test de rolcheck niet.
            json={"ticket_ref": "TOOL-SELFREJECT", "reason": "buiten mandaat van deze agent"},
        )

        assert resp.status_code == 403, (
            f"Een gewone tenantgebruiker mag afwijzen (status {resp.status_code}). Afwijzen is ook "
            "een toezichtshandeling: wie kan afwijzen kan werk van een collega blokkeren."
        )

    def test_an_admin_cannot_approve_their_own_request(self, admin_client, monkeypatch):
        """Met vier ogen AAN toetst de router een relatie, niet alleen een rol (ADR-039).

        Tot 2026-10-04 gold dit altijd (ADR-036 OP-70). Besluit Rakesh in ADR-039: zelf beslissen
        mag, tenzij de tenant vier ogen aanzet voor die actie. Deze test zet het AAN; de stand
        UIT staat in `tests/unit/api/test_zelfgoedkeuring_volgt_de_vier_ogen_instelling.py`.
        De admin-fixture heeft `id=1`, dus een ticket met `_requested_by="1"` is van hemzelf.
        """
        _vier_ogen_aan(monkeypatch)
        _seed_ticket("TOOL-OWN", tenant_id=1, status="pending")
        _mock_db_tickets["TOOL-OWN"].payload = {"_requested_by": "1"}

        resp = admin_client.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-OWN"}
        )

        assert resp.status_code == 403, (
            f"Een beheerder keurt zijn EIGEN verzoek goed (status {resp.status_code}). Dan is de "
            "menselijke controle uit ADR-015 een handtekening onder je eigen aanvraag."
        )

    def test_an_admin_cannot_reject_their_own_request(self, admin_client, monkeypatch):
        """Afwijzen is ook een toezichtshandeling; zelfde relatie, zelfde grens (vier ogen aan)."""
        _vier_ogen_aan(monkeypatch)
        _seed_ticket("TOOL-OWN-REJ", tenant_id=1, status="pending")
        _mock_db_tickets["TOOL-OWN-REJ"].payload = {"_requested_by": "1"}

        resp = admin_client.post(
            "/api/v1/tools/hitl/reject",
            json={"ticket_ref": "TOOL-OWN-REJ", "reason": "toch maar niet, ik trek het in"},
        )

        assert resp.status_code == 403

    def test_an_admin_can_still_approve_someone_elses_request(self, admin_client):
        """Vangnet: alles weigeren zou de twee tests hierboven ook groen maken.

        Zonder deze assertie is "niemand mag ooit goedkeuren" een geldige oplossing, en dan staat
        de hele wachtrij stil.
        """
        _seed_ticket("TOOL-OTHER", tenant_id=1, status="pending")
        _mock_db_tickets["TOOL-OTHER"].payload = {"_requested_by": "999"}

        resp = admin_client.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-OTHER"}
        )

        assert resp.status_code == 200, (
            f"Een beheerder kan het verzoek van een ANDER niet goedkeuren (status "
            f"{resp.status_code}). Dan is de wachtrij onwerkbaar."
        )

    def test_a_normal_user_cannot_list_pending_tickets(self, client, procesrecht_poort):
        procesrecht_poort(set())
        """De lijst hoort bij het handelen, niet bij het lezen.

        `/hitl/pending` geeft het ONBEWERKTE `tool_input` van elk openstaand ticket. Voor de tools
        die een ticket krijgen -- HIGH-risk, dus `local__send_email` -- is dat de klaartekst van de
        aanroep, inclusief het volledige bericht aan een klant dat een collega heeft opgesteld.
        Zolang alleen een beheerder kan goedkeuren, heeft niemand anders die waarden nodig.
        """
        _seed_ticket("TOOL-PEND-SECRET", tenant_id=1, status="pending")

        resp = client.get("/api/v1/tools/hitl/pending")

        assert resp.status_code == 403, (
            f"Een gewone tenantgebruiker leest de openstaande tickets (status {resp.status_code}), "
            "inclusief het onbewerkte tool_input van collega's."
        )

    def test_an_approver_still_sees_the_real_values(self, admin_client):
        """De andere richting -- AI Act art. 14: wie goedkeurt moet zien wat hij goedkeurt.

        Zonder deze test is "sluit tool_input overal uit" een geldige oplossing, en dan keurt een
        mens een actie goed zonder te weten wat er gebeurt. Dat is dezelfde eigenschap die de
        vorige test op iedereen borgde; hij hoort op de GOEDKEURDER te staan.
        """
        _seed_ticket("TOOL-PEND-VISIBLE", tenant_id=1, status="pending")

        resp = admin_client.get("/api/v1/tools/hitl/pending")

        assert resp.status_code == 200, (
            "De goedkeurder kan het goedkeuringsoppervlak niet meer bereiken. Dan kan niemand "
            "nog goedkeuren en is de HIGH-risk-poort permanent dicht."
        )
        body = resp.json()
        tickets = body.get("data", body) if isinstance(body, dict) else body
        assert tickets, "geen tickets teruggekregen -- dan toetst deze test niets"
        assert any("tool_input" in ticket for ticket in tickets), (
            "Het goedkeuringsoppervlak toont `tool_input` niet meer. Dat is de art.-14-uitzondering "
            "op de redactie; hem hier weghalen maakt het toezicht een formaliteit."
        )


@pytest.mark.unit
class TestEveryDecisionLeavesAnImmutableTrace:
    """Een HIGH-risk beslissing hoort een ADR-019 ketenregel te krijgen (ADR-036 OP-71).

    Wat er hiervoor overbleef: een `logger.info` en een JSONB-kolom die elke latere UPDATE kan
    herschrijven, plus `resolved_by` als FK. Voor een toezichtsrecord waarvan de hele
    rechtvaardiging is dat een MENS aantoonbaar heeft besloten (AI Act art. 14), is dat de zwakste
    schakel in de keten -- en het is precies het stuk dat een auditor wil zien.

    De schrijfactie staat NA de primaire commit en in `best_effort`: een falende auditregel mag een
    reeds genomen beslissing niet terugdraaien (backend-patterns par. 3).
    """

    @staticmethod
    def _audit_calls(monkeypatch) -> list:
        calls: list = []

        async def _capture(**kwargs):
            calls.append(kwargs)
            return True

        monkeypatch.setattr(
            "src.core.api.v1.tool_broker.hitl_router.AuditService.log_event",
            staticmethod(_capture),
        )
        return calls

    def test_approving_writes_an_audit_entry(self, admin_client, monkeypatch):
        calls = self._audit_calls(monkeypatch)
        _seed_ticket("TOOL-AUDIT-OK", tenant_id=1, status="pending")
        _mock_db_tickets["TOOL-AUDIT-OK"].payload = {"_requested_by": "999"}

        resp = admin_client.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-AUDIT-OK"}
        )

        assert resp.status_code == 200
        assert calls, (
            "Goedkeuren van een HIGH-risk actie laat geen ADR-019 ketenregel achter. Wat overblijft "
            "is een logregel en een JSONB-kolom die overschreven kan worden."
        )
        entry = calls[0]
        assert entry["action"] == "approved"
        # `resource` draagt sinds ADR-036 H-2 ook een digest over het bewijs dat buiten
        # `_compute_hash` valt. Het voorvoegsel blijft ongewijzigd, zodat bestaande
        # prefix-queries op `hitl_ticket:` blijven werken.
        assert entry["resource"].startswith("hitl_ticket:TOOL-AUDIT-OK|ev=")
        assert entry["tenant_id"] == 1

    def test_rejecting_writes_an_audit_entry(self, admin_client, monkeypatch):
        """Afwijzen is net zo goed een toezichtshandeling.

        Zonder deze regel is alleen het GOEDKEUREN navolgbaar en blijft "waarom is dit geweigerd"
        buiten het bewijs -- terwijl juist een weigering laat zien dat het toezicht werkt.
        """
        calls = self._audit_calls(monkeypatch)
        _seed_ticket("TOOL-AUDIT-NO", tenant_id=1, status="pending")
        _mock_db_tickets["TOOL-AUDIT-NO"].payload = {"_requested_by": "999"}

        resp = admin_client.post(
            "/api/v1/tools/hitl/reject",
            json={"ticket_ref": "TOOL-AUDIT-NO", "reason": "buiten mandaat van deze agent"},
        )

        assert resp.status_code == 200
        assert calls, "Afwijzen laat geen ADR-019 ketenregel achter."
        assert calls[0]["action"] == "rejected"

    def test_the_audit_entry_carries_no_model_written_text(self, admin_client, monkeypatch):
        """Vangnet: de ketenregel mag zelf geen nieuw klaartekstpad worden.

        Zonder deze assertie is "zet de hele payload in de metadata" een geldige oplossing, en dan
        is de auditketen -- de plek die per definitie onuitwisbaar is -- het achtste bewarende pad
        voor door een model geschreven tekst.
        """
        calls = self._audit_calls(monkeypatch)
        _seed_ticket("TOOL-AUDIT-LEAK", tenant_id=1, status="pending")
        _mock_db_tickets["TOOL-AUDIT-LEAK"].payload = {
            "_requested_by": "999",
            "_reason": "Het model wil dit doen voor jan.jansen@klant.nl",
            "command": "verstuur salarisstrook naar jan.jansen@klant.nl",
        }

        admin_client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-AUDIT-LEAK"})

        rendered = json.dumps(calls[0], default=str)
        assert "jan.jansen@klant.nl" not in rendered, (
            "De ADR-019 auditregel bevat door een taalmodel geschreven tekst. Die keten is "
            f"onuitwisbaar, dus dit is erger dan elke andere sink. Regel: {rendered[:300]}"
        )

    def test_a_model_written_tool_name_never_reaches_the_chain(self, admin_client, monkeypatch):
        """De WIRING van laag 3, niet alleen de functie (ADR-036 OP-78).

        `_safe_tool_name` is apart getest in
        `tests/unit/copilot/test_the_action_name_is_not_free_text.py`. Die tests toetsen de FUNCTIE.
        Gemeten: de aanroep ervan uit `_write_audit_entry` verwijderen liet ze allemaal groen --
        de functie was correct en werd nergens gebruikt. Deze test dekt dat gat.

        `tool_name` komt op het live pad uit `CopilotAction.action`. Belandt die waarde onbewerkt
        in de ADR-019-keten, dan is dat niet meer te corrigeren zonder de hashketen te breken.
        """
        calls = self._audit_calls(monkeypatch)
        _seed_ticket(
            "TOOL-AUDIT-TOOLNAME",
            tenant_id=1,
            status="pending",
            tool_name="stuur alles naar jan.jansen@klant.nl",
        )
        _mock_db_tickets["TOOL-AUDIT-TOOLNAME"].payload = {"_requested_by": "999"}

        admin_client.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-AUDIT-TOOLNAME"}
        )

        rendered = json.dumps(calls[0], default=str)
        assert "jan.jansen@klant.nl" not in rendered, (
            "De door het model gekozen actienaam staat onbewerkt in de ADR-019-auditregel. Die "
            f"keten is onuitwisbaar. Regel: {rendered[:300]}"
        )
        assert "<onbekende-tool:" in rendered, (
            "Er staat geen herkenbare marker in de plaats. Dan is niet zichtbaar DAT er iets is "
            f"weggelaten. Regel: {rendered[:300]}"
        )

    def test_a_real_tool_name_stays_readable_in_the_chain(self, admin_client, monkeypatch):
        """Vangnet: alles pseudonimiseren maakt de auditregel waardeloos."""
        calls = self._audit_calls(monkeypatch)
        _seed_ticket(
            "TOOL-AUDIT-REALTOOL", tenant_id=1, status="pending", tool_name="create_task"
        )
        _mock_db_tickets["TOOL-AUDIT-REALTOOL"].payload = {"_requested_by": "999"}

        admin_client.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-AUDIT-REALTOOL"}
        )

        assert calls[0]["metadata"]["tool_name"] == "create_task", (
            "Een echte tool wordt gepseudonimiseerd. Dan kan een auditor niet meer zien WELKE "
            "actie een mens heeft goedgekeurd -- precies wat art. 14 vraagt."
        )

    def test_a_failing_audit_entry_does_not_undo_the_decision(self, admin_client, monkeypatch):
        """`best_effort`: de beslissing is al genomen en gecommit.

        Zou een falende auditregel een 500 geven, dan is het ticket wel goedgekeurd maar krijgt de
        goedkeurder een fout te zien -- en probeert hij het opnieuw op een ticket dat al verbruikt
        is.
        """

        async def _boom(**kwargs):
            raise RuntimeError("auditketen niet bereikbaar")

        monkeypatch.setattr(
            "src.core.api.v1.tool_broker.hitl_router.AuditService.log_event",
            staticmethod(_boom),
        )
        _seed_ticket("TOOL-AUDIT-FAIL", tenant_id=1, status="pending")
        _mock_db_tickets["TOOL-AUDIT-FAIL"].payload = {"_requested_by": "999"}

        resp = admin_client.post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-AUDIT-FAIL"}
        )

        assert resp.status_code == 200, (
            f"Een falende auditregel geeft {resp.status_code}. De beslissing is dan wel genomen "
            "maar de goedkeurder ziet een fout, en probeert het opnieuw op een verbruikt ticket."
        )


@pytest.mark.unit
class TestTheStateChangingRoutesRequireACsrfToken:
    """Beide POST-routes moeten een CSRF-token eisen (ADR-036 OP-72).

    `get_current_user` accepteert het `access_token`-cookie. Zonder CSRF-controle is een
    cross-site POST dus alleen afgedekt door `SameSite` -- een eigenschap van de browser, geen
    controle van ons, en niet iets waar een toezichtsgate op mag rusten. Vergelijkbare endpoints
    (`copilot/api/turn_endpoint.py`, `api/v1/missions/lifecycle_router.py`) hebben deze dependency
    al; deze twee waren de uitzondering.

    Deze klasse bouwt bewust een app ZONDER de override die `_make_app` zet -- anders zou hij de
    afwezigheid van de controle niet kunnen zien.
    """

    @staticmethod
    def _app_without_csrf_override() -> FastAPI:
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(hitl_router)
        app.dependency_overrides[get_current_user] = lambda: _make_admin(tenant_id=1)
        app.dependency_overrides[get_db] = lambda: AsyncMock()
        return app

    def test_approve_refuses_a_request_without_a_csrf_token(self):
        client = TestClient(self._app_without_csrf_override())

        resp = client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-CSRF"})

        assert resp.status_code == 403, (
            f"Goedkeuren lukt zonder CSRF-token (status {resp.status_code}). De sessie loopt via "
            "een cookie, dus een andere site kan dit verzoek namens een ingelogde beheerder doen."
        )

    def test_reject_refuses_a_request_without_a_csrf_token(self):
        client = TestClient(self._app_without_csrf_override())

        resp = client.post(
            "/api/v1/tools/hitl/reject",
            json={"ticket_ref": "TOOL-CSRF", "reason": "buiten mandaat van deze agent"},
        )

        assert resp.status_code == 403, (
            f"Afwijzen lukt zonder CSRF-token (status {resp.status_code}). Ook een afwijzing is "
            "een toezichtshandeling: wie die kan forceren blokkeert werk van een collega."
        )

    def test_the_read_routes_do_not_require_a_csrf_token(self):
        """Vangnet: CSRF hoort NIET op leesroutes.

        Zonder deze assertie is "zet hem overal op" een geldige oplossing, en dan moet een
        goedkeurder een token ophalen om alleen maar te kijken wat er openstaat.
        """
        client = TestClient(self._app_without_csrf_override())

        resp = client.get("/api/v1/tools/hitl/pending")

        assert resp.status_code != 403 or "CSRF" not in resp.text, (
            "De lijst met openstaande tickets eist een CSRF-token. Dat is een leesactie; die "
            "verandert niets en hoort die drempel niet te hebben."
        )


@pytest.mark.unit
class TestApprovingActuallyExecutes:
    """Goedkeuren voert de actie uit (ADR-036 OP-89).

    **Waarom dit de belangrijkste test van deze feature is.** Tot 2026-08-07 zette een goedkeuring
    het ticket op `approved` en daar hield het op: `git grep "_hitl_ticket_ref"` over `src/` en
    `frontend/src/` liet zien dat NIETS die verwijzing ooit in een uitvoerpayload schreef. Een mens
    drukte op goedkeuren en de actie draaide nooit. Alle begrenzing die deze sprint is gebouwd --
    binding aan tool en parameters, eenmalig verbruik, vervaltermijn -- zat in een doodlopende
    straat.

    Besluit Rakesh: direct uitvoeren bij goedkeuren, daarna wissen. Dat is de enige volgorde die
    het wisbesluit uit OP-47 verenigt met een werkende lus, want na het wissen zijn de parameters
    weg.
    """

    def test_approving_calls_the_broker_with_the_approved_action(self):
        _seed_ticket("TOOL-EXEC", tenant_id=1, tool_name="delete_task")
        _mock_db_tickets["TOOL-EXEC"].payload = {
            "task_id": "42",
            "_decision_id": "d1",
            # Een ANDERE gebruiker dan de goedkeurder: de zelf-goedkeuringscheck uit OP-70
            # weigert terecht wie zijn eigen verzoek beoordeelt.
            "_requested_by": "99",
        }
        client = TestClient(_make_app(_make_admin(tenant_id=1)))

        resp = client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-EXEC"})

        assert resp.status_code == 200, resp.text
        assert len(_UITGEVOERD) == 1, (
            "Goedkeuren heeft de broker niet aangeroepen. Dan springt het ticket op `approved` en "
            "gebeurt er verder niets -- precies de doodlopende straat uit OP-89."
        )
        aanroep = _UITGEVOERD[0]
        assert aanroep["tool_name"] == "delete_task"
        assert aanroep["payload"]["task_id"] == "42", (
            "De goedgekeurde parameters zijn niet meegegeven. `repo.approve` wist de payload, dus "
            "ze moeten VOOR die aanroep zijn vastgehouden."
        )
        assert aanroep["payload"]["_hitl_ticket_ref"] == "TOOL-EXEC", (
            "Zonder de ticketverwijzing verzilvert de poort het ticket niet, en blijft de "
            "goedkeuring herbruikbaar."
        )
        assert aanroep["context"]["tenant_id"] == 1
        # DE UITVOERENDE IDENTITEIT (ADR-036 OP-103). Zonder deze assertie kon `agent_id` op iets
        # anders worden gezet en bleef de hele suite groen -- beide blinde reviewers toonden dat
        # onafhankelijk aan met `agent_id="admin"` respectievelijk `"hitl_approver"`. Met de echte
        # broker heeft zo'n identiteit geen profiel in `tool_permissions.yml`, dus dan weigert de
        # default-deny ELKE goedgekeurde actie: de feature is stil kapot.
        #
        # OP-90 controleert bij het AANMAKEN van een ticket of deze identiteit de tool mag draaien.
        # Wijkt de uitvoerende identiteit daarvan af, dan toetst die controle iets anders dan wat
        # er gebeurt -- en dat is precies het soort scheefgroei dat deze reeks kenmerkt.
        # De LETTERLIJKE waarde en niet `_UITVOERENDE_IDENTITEIT` (ADR-036 BLOCKER-1,
        # 2026-08-09). Met de constante beweegt deze assertie mee met wat ze bewaakt: hernoem de
        # constante en het aanroeppunt tegelijk, en alles blijft groen terwijl er in
        # `config/tool_permissions.yml` geen profiel met die nieuwe naam bestaat. De constante
        # zelf wordt vastgepind in
        # `tests/unit/tool_broker/test_the_executing_identity_has_permission.py`.
        assert aanroep["agent_id"] == "copilot", (
            f"De actie wordt uitgevoerd als {aanroep['agent_id']!r} in plaats van 'copilot'. De "
            "permissiecheck bij het aanmaken toetst dan een andere identiteit dan die het straks "
            "uitvoert."
        )

        # HIER STOND EEN BACKSTOP DIE NOOIT KON FALEN (ADR-036 BLOCKER-1).
        #
        #     assert ToolPermissionManager().is_tool_allowed(aanroep["agent_id"], ...)
        #
        # De autouse-fixture `_allow_all_tools` op regel 39 patcht `is_tool_allowed` op de
        # KLASSE, dus ook voor een vers object en voor elke test in dit bestand. Die assertie
        # was daarmee `assert True`. Een blinde reviewer zette de uitvoerende identiteit op iets
        # zonder profiel: 1538 tests bleven groen, terwijl in productie elk HIGH-risk ticket dan
        # een PermissionError geeft.
        #
        # De echte controle staat nu in een module ZONDER die fixture:
        # `tests/unit/tool_broker/test_the_executing_identity_has_permission.py`.
        # Verplaatsen en niet repareren: zolang die fixture hier staat, is elke permissie-
        # assertie in dit bestand decoratie.

    def test_the_response_says_whether_it_executed(self):
        _seed_ticket("TOOL-EXEC2", tenant_id=1, tool_name="delete_task")
        client = TestClient(_make_app(_make_admin(tenant_id=1)))

        resp = client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-EXEC2"})

        assert resp.json()["executed"] is True, (
            "Het antwoord zegt niet of de actie is uitgevoerd. Zonder dat kan de interface een "
            "goedkeuring tonen als geslaagd terwijl er niets is gebeurd."
        )

    def test_a_failing_execution_does_not_undo_the_approval(self):
        """Een mens heeft besloten; dat feit blijft staan.

        En het antwoord blijft 200: een 500 zou de beheerder laten denken dat zijn besluit niet is
        aangekomen, terwijl het wel degelijk in de keten staat.
        """
        _seed_ticket("TOOL-EXEC3", tenant_id=1, tool_name="delete_task")
        app = _make_app(_make_admin(tenant_id=1))

        from src.core.api.v1.tool_broker.dependencies import get_tool_broker_service

        class _KapotteBroker:
            async def execute_tool(self, **_kwargs):
                raise RuntimeError("de tool viel om")

        app.dependency_overrides[get_tool_broker_service] = lambda: _KapotteBroker()
        resp = TestClient(app).post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-EXEC3"}
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["executed"] is False
        assert _mock_db_tickets["TOOL-EXEC3"].status == "approved", (
            "De goedkeuring is teruggedraaid omdat de uitvoering faalde. Het besluit van een mens "
            "is een feit dat in de keten hoort, ook als wat erna kwam misging."
        )

    def test_the_error_text_never_reaches_the_client(self):
        """De fouttekst kan payload-inhoud bevatten -- daar gaat deze hele feature over (OP-29)."""
        _seed_ticket("TOOL-EXEC4", tenant_id=1, tool_name="delete_task")
        app = _make_app(_make_admin(tenant_id=1))

        from src.core.api.v1.tool_broker.dependencies import get_tool_broker_service

        geheim = "salarisstrook van jan.jansen@klant.nl"

        class _LekkendeBroker:
            async def execute_tool(self, **_kwargs):
                raise RuntimeError(geheim)

        app.dependency_overrides[get_tool_broker_service] = lambda: _LekkendeBroker()
        resp = TestClient(app).post(
            "/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-EXEC4"}
        )

        assert geheim not in resp.text, (
            "De fouttekst van de tool staat in het antwoord. Die kan door een taalmodel geschreven "
            "parameters bevatten."
        )
        assert resp.json()["execution_error"] == "RuntimeError", (
            "Alleen het TYPE van de fout hoort naar buiten te gaan, en dat wel -- anders kan "
            "niemand zien waarom het misging."
        )


class TestModelWrittenKeysNeverReachTheTool:
    """Model-geschreven `user_id`/`tenant_id` blijven uit de uitvoering (ADR-036 OP-105).

    **Deze fix had nul tests.** Gemeten 2026-08-09: `parameters_voor_uitvoering` kwam nergens in
    `tests/` voor, en het weghalen van `and k not in BROKER_INJECTED_KEYS` uit
    `hitl_router.py:371` liet de hele suite groen. De enige test die `BROKER_INJECTED_KEYS`
    noemt bewaakt iets anders (OP-75, of de verzameling klopt met wat `execute_tool` injecteert).

    Waarom het ertoe doet: `execute_tool` overschrijft die sleutels ALLEEN als de context ze
    bevat, en `context["user_id"]` wordt alleen gezet als `_requested_by` een zuiver getal is.
    Ontbreekt dat veld -- oudere tickets -- dan is de waarde VAN HET MODEL wat de tool krijgt.

    **Mutatietest (2026-08-09):** `and k not in BROKER_INJECTED_KEYS` uit `hitl_router.py`
    gehaald -> ROOD. Terug -> GROEN. En de omgekeerde richting: een gewone parameter
    (`task_id`) moet WEL doorkomen, anders is "gooi alles weg" een geldige oplossing.
    """

    def test_the_model_written_identity_keys_are_stripped(self):
        _seed_ticket("TOOL-OP105", tenant_id=1, tool_name="delete_task")
        _mock_db_tickets["TOOL-OP105"].payload = {
            "task_id": "42",
            # Door een taalmodel geschreven -- dit is precies wat OP-105 tegenhoudt.
            "user_id": 999999,
            "tenant_id": 424242,
            "_requested_by": "99",
        }
        client = TestClient(_make_app(_make_admin(tenant_id=1)))

        resp = client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-OP105"})

        assert resp.status_code == 200, resp.text
        assert len(_UITGEVOERD) == 1
        payload = _UITGEVOERD[0]["payload"]

        # Toets tegen de LITERALS en niet alleen tegen BROKER_INJECTED_KEYS: die frozenset
        # leegmaken zou anders de test groen maken terwijl het gat terug is.
        for sleutel in ("user_id", "tenant_id"):
            assert sleutel not in payload, (
                f"De model-geschreven {sleutel!r} staat in de payload die de tool krijgt "
                f"(waarde {payload.get(sleutel)!r}). `execute_tool` overschrijft die sleutel "
                "alleen als de context hem bevat; bij een ouder ticket zonder `_requested_by` "
                "is de waarde van het model dus wat de tool uitvoert (ADR-036 OP-105)."
            )

        from src.core.tool_broker.redaction import BROKER_INJECTED_KEYS

        assert not (set(payload) & set(BROKER_INJECTED_KEYS)), (
            f"Payload bevat nog door de broker geinjecteerde sleutels: "
            f"{sorted(set(payload) & set(BROKER_INJECTED_KEYS))}."
        )

    def test_an_ordinary_parameter_still_gets_through(self):
        """De andere richting: zonder deze test is 'gooi alles weg' een geldige oplossing."""
        _seed_ticket("TOOL-OP105B", tenant_id=1, tool_name="delete_task")
        _mock_db_tickets["TOOL-OP105B"].payload = {
            "task_id": "42",
            "reden": "opruimen",
            "user_id": 999999,
            "_requested_by": "99",
        }
        client = TestClient(_make_app(_make_admin(tenant_id=1)))

        resp = client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": "TOOL-OP105B"})

        assert resp.status_code == 200, resp.text
        payload = _UITGEVOERD[0]["payload"]
        assert payload["task_id"] == "42"
        assert payload["reden"] == "opruimen", (
            "Een gewone, goedgekeurde parameter komt niet meer door. Het filter gooit te veel "
            "weg en de goedgekeurde actie draait met andere argumenten dan de mens zag."
        )


class TestOnlyPlainAsciiDigitsCountAsAUserNumber:
    """`_requested_by` telt alleen als gebruiker bij zuivere ASCII-cijfers (ADR-036 OP-106).

    **Ook deze fix had nul tests.** Gemeten 2026-08-09: `_als_gebruikersnummer` kwam nergens in
    `tests/` voor. `isascii() and isdecimal()` terugdraaien naar `isdigit()` -- exact de
    regressie die de ADR als gesloten registreert -- liet de hele suite groen.

    Twee verschillende gevolgen, en daarom twee soorten invoer in deze test:
    - Arabisch-Indische cijfers: `isdigit()` is True en `int()` slaagt, dus "zo'n cijfer" wordt
      stil gebruiker 3, terwijl `_refuse_self_approval` STRINGS vergelijkt en dus iets anders
      concludeert dan de uitvoering.
    - Superscripts: `isdigit()` is True maar `int()` gooit een ValueError. Die wordt nergens
      gevangen, dus een 500 NADAT de goedkeuring al is vastgelegd.

    **Mutatietest (2026-08-09):** `isascii() and isdecimal()` -> `isdigit()` -> ROOD op beide
    niet-westerse gevallen. Terug -> GROEN, en het gewone getal blijft werken.
    """

    def test_plain_digits_are_accepted(self):
        from src.core.api.v1.tool_broker.hitl_router import _als_gebruikersnummer

        assert _als_gebruikersnummer("99") == 99
        assert _als_gebruikersnummer(" 42 ") == 42

    def test_non_western_digits_are_refused(self):
        from src.core.api.v1.tool_broker.hitl_router import _als_gebruikersnummer

        # Arabisch-Indisch "3": isdigit() True, int() slaagt -> zou stil gebruiker 3 worden.
        assert _als_gebruikersnummer("\u0663") is None, (
            "Een Arabisch-Indisch cijfer telt als gebruikersnummer. `_refuse_self_approval` "
            "vergelijkt strings, dus die concludeert iets anders dan de uitvoering doet."
        )
        # Superscript twee: isdigit() True, int() gooit ValueError -> 500 NA de goedkeuring.
        assert _als_gebruikersnummer("\u00b2") is None, (
            "Een superscript telt als cijfer. `int()` gooit daarop een ValueError die nergens "
            "gevangen wordt: een 500 nadat de goedkeuring al is vastgelegd."
        )

    def test_nonsense_is_refused(self):
        from src.core.api.v1.tool_broker.hitl_router import _als_gebruikersnummer

        for waarde in ("", None, "iemand@example.com", "12a", "-1x"):
            assert _als_gebruikersnummer(waarde) is None


class TestTheAuditHashCoversTheEvidence:
    """De onuitwisbare keten dekt WIE goedkeurde en WAT (ADR-036 H-2).

    **De bevinding.** `HashChainVerifier._compute_hash` dekt `tenant_id`, `action`, `resource`,
    `timestamp` en de vorige hash. `event_metadata`, `description` en `user_id` staan daarbuiten.
    Gemeten: twee auditregels met een verschillende `tool_name` EN een verschillende `user_id`
    leverden dezelfde hash op. Precies het bewijs waarop de art.-14-claim rust -- WIE keurde een
    HIGH-risk actie goed, en WELKE aanroep -- was achteraf te wijzigen zonder dat de
    ketenverificatie brak.

    **Deze tests lopen over de ECHTE producent.** Zelf twee `resource`-strings bouwen en die aan
    `_compute_hash` voeren, bewijst alleen dat die functie injectief is over `resource` -- en dat
    was al zo. Dan is `hitl_router.py` terug te draaien naar `f"hitl_ticket:{ref}"` en blijft de
    test groen. Dat is de vorm "een test die zijn eigen invoer aan beide kanten verzint" uit
    quality-gates.md. Daarom gaat alles hieronder door de approve-endpoint heen.

    **De tijdstempel wordt vastgezet.** Zonder dat bewijst een verschil in hashes alleen dat de
    klok loopt -- de valkuil die in deze reeks al een keer een guard hol maakte
    (`assert sql_one != sql_two` op SQL met microseconden erin).

    **Mutatietest (2026-08-09):** `resource` in `hitl_router.py` terug naar
    `f"hitl_ticket:{ticket_ref}"` -> ROOD op beide hashtests EN op de manipulatietest.
    """

    VAST_TIJDSTIP = datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)

    @staticmethod
    def _audit_calls(monkeypatch) -> list:
        calls: list = []

        async def _capture(**kwargs):
            calls.append(kwargs)
            return True

        monkeypatch.setattr(
            "src.core.api.v1.tool_broker.hitl_router.AuditService.log_event",
            staticmethod(_capture),
        )
        return calls

    def _hash_van(self, entry: dict) -> str:
        """De ketenhash van een auditregel, met een VASTE tijdstempel."""
        from src.core.governance.hash_chain import HashChainVerifier
        from src.core.governance.models import AuditLog

        rij = AuditLog(
            tenant_id=entry["tenant_id"],
            action=entry["action"],
            resource=entry["resource"],
            timestamp=self.VAST_TIJDSTIP,
        )
        return HashChainVerifier(db_session=None)._compute_hash(rij, "vorige-hash")

    def _keur_goed(self, monkeypatch, ticket_ref: str, tool_name: str, gebruiker_id: int) -> dict:
        calls = self._audit_calls(monkeypatch)
        _seed_ticket(ticket_ref, tenant_id=1, status="pending", tool_name=tool_name)
        _mock_db_tickets[ticket_ref].payload = {"_requested_by": "999"}
        goedkeurder = UserResponse(
            id=gebruiker_id, email=f"admin{gebruiker_id}@test.com", tenant_id=1,
            roles=["admin"], scopes=[],
        )
        client = TestClient(_make_app(goedkeurder))

        resp = client.post("/api/v1/tools/hitl/approve", json={"ticket_ref": ticket_ref})

        assert resp.status_code == 200, resp.text
        assert calls, "Geen auditregel geschreven."
        return calls[0]

    def test_a_different_tool_gives_a_different_chain_hash(self, monkeypatch):
        """WAT er is goedgekeurd moet de keten raken."""
        een = self._keur_goed(monkeypatch, "TOOL-H2-A", "delete_task", 1)
        twee = self._keur_goed(monkeypatch, "TOOL-H2-A", "update_task", 1)

        assert self._hash_van(een) != self._hash_van(twee), (
            "Twee goedkeuringen van een ANDERE tool leveren dezelfde ketenhash op. De toolnaam "
            "zit alleen in `event_metadata`, en dat veld valt buiten `_compute_hash` -- dus is "
            "achteraf te wijzigen zonder dat de verificatie breekt (ADR-036 H-2)."
        )

    def test_a_different_approver_gives_a_different_chain_hash(self, monkeypatch):
        """WIE goedkeurde moet de keten raken -- dit is de kern van art. 14."""
        een = self._keur_goed(monkeypatch, "TOOL-H2-B", "delete_task", 1)
        twee = self._keur_goed(monkeypatch, "TOOL-H2-B", "delete_task", 2)

        assert self._hash_van(een) != self._hash_van(twee), (
            "Twee goedkeuringen door een ANDERE mens leveren dezelfde ketenhash op. `user_id` "
            "valt buiten `_compute_hash`, dus wie een HIGH-risk actie goedkeurde is achteraf te "
            "wijzigen zonder dat de verificatie breekt (ADR-036 H-2)."
        )

    def test_tampering_with_the_stored_metadata_is_detected(self, monkeypatch):
        """De digest wordt ook DAADWERKELIJK nagerekend -- anders is binden theater.

        Dit is de test die de Gate 2-review eiste: niet "de digest is een functie van de
        toolnaam" (dat is zelf-verzonnen invoer aan beide kanten), maar: neem de OPGESLAGEN rij,
        wijzig het bewijs erin, en toon dat de verificatie dat betrapt.
        """
        from src.core.governance.hash_chain import HashChainVerifier
        from src.core.governance.models import AuditLog

        entry = self._keur_goed(monkeypatch, "TOOL-H2-C", "delete_task", 1)
        rij = AuditLog(
            tenant_id=entry["tenant_id"],
            action=entry["action"],
            resource=entry["resource"],
            user_id=entry["user_id"],
            timestamp=self.VAST_TIJDSTIP,
            event_metadata=dict(entry["metadata"]),
        )
        verifier = HashChainVerifier(db_session=None)

        assert verifier._verify_bound_evidence(rij) is True, (
            "De ongewijzigde rij rekent al niet na. Dan meet de manipulatietest hieronder niets."
        )

        # DE MANIPULATIE: de toolnaam in de opgeslagen metadata wijzigen. `resource` blijft
        # ongemoeid, dus de ketenhash klopt nog -- zonder de digest zou niets dit zien.
        rij.event_metadata = {**rij.event_metadata, "tool_name": "iets_onschuldigs"}
        assert verifier._verify_bound_evidence(rij) is False, (
            "De toolnaam in de opgeslagen metadata is gewijzigd en de verificatie merkt het "
            "niet. Dan is het bewijs wel gebonden maar wordt de binding nooit getoetst."
        )

        # En de goedkeurder, want dat is waar art. 14 om draait.
        rij.event_metadata = dict(entry["metadata"])
        rij.user_id = 424242
        assert verifier._verify_bound_evidence(rij) is False, (
            "De goedkeurder is gewijzigd en de verificatie merkt het niet."
        )

    def test_an_ordinary_audit_row_is_not_reported_as_tampered(self, monkeypatch):
        """De andere richting: 'niets na te rekenen' mag NOOIT 'manipulatie' betekenen.

        Zonder deze helft zou elke gewone auditregel -- en elke HITL-regel van voor deze
        wijziging -- als gebroken gemeld worden, en dan is 'weiger alles' een geldige oplossing.
        """
        from src.core.governance.hash_chain import HashChainVerifier
        from src.core.governance.models import AuditLog

        verifier = HashChainVerifier(db_session=None)

        gewoon = AuditLog(tenant_id=1, action="login", resource="user:7", timestamp=self.VAST_TIJDSTIP)
        assert verifier._verify_bound_evidence(gewoon) is None

        oud = AuditLog(
            tenant_id=1, action="approved", resource="hitl_ticket:TOOL-OUD",
            timestamp=self.VAST_TIJDSTIP,
        )
        assert verifier._verify_bound_evidence(oud) is None, (
            "Een HITL-regel van voor deze wijziging heeft geen `|ev=`-deel en is dus niet "
            "gedekt. Die als manipulatie melden is onwaar."
        )
