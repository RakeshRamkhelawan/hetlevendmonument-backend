"""Unit tests for Focus Builder governance gate.

Tests verify that the AgentCouncil is consulted before any flow is
executed via ActivePieces and that blocked/HITL flows are correctly handled.

Uses TestClient + dependency_overrides to bypass the rate limiter and
inject mock dependencies without needing a real database or ActivePieces.
"""

import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.core.copilot.council.types import DecisionVerdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_decision(verdict: DecisionVerdict, explanation: str = "Test explanation") -> MagicMock:
    decision = MagicMock()
    decision.verdict = verdict
    decision.explanation_for_user = explanation
    decision.decision_id = uuid4()
    return decision


def _make_app(council_mock: MagicMock, service_mock: MagicMock) -> FastAPI:
    """Build a minimal FastAPI app with the focus-builder router + mocked deps."""
    from src.core.api.v1.focus_builder.router import router, get_focus_builder_service
    from src.core.api.v1.focus_builder.dependencies import get_focus_builder_council
    from src.core.auth.dependencies import get_current_user_dependency
    from src.core.auth.auth_service import UserResponse
    from src.core.middleware.rate_limiter import get_limiter
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    app = FastAPI()

    # Inject mock tenant context so ORM hook stays happy
    from src.core.middleware.tenant_context import set_tenant_id

    @app.middleware("http")
    async def add_tenant(request: Request, call_next: Any) -> Any:
        set_tenant_id(10)
        return await call_next(request)

    # Replace rate limiter with a no-op so tests are not throttled
    no_op_limiter = Limiter(key_func=get_remote_address, default_limits=[])
    app.state.limiter = no_op_limiter

    app.include_router(router, prefix="/api/v1")

    # Override dependencies
    mock_user = UserResponse(
        id=1,
        email="test@example.com",
        tenant_id=10,
        is_superuser=False,
    )
    app.dependency_overrides[get_current_user_dependency] = lambda: mock_user
    app.dependency_overrides[get_focus_builder_service] = lambda: service_mock
    app.dependency_overrides[get_focus_builder_council] = lambda: council_mock
    app.dependency_overrides[get_limiter] = lambda: no_op_limiter
    # Deze test meet de Council-poort. De rolcontrole `workflows:publish` (wfb-dag1 stap 1) heeft
    # eigen tests (tests/integration/api/test_workflow_publicatierecht_per_rol.py) en leest het
    # echte token, dat hier niet bestaat; daarom vervangen, net als de gebruiker hierboven.
    from fastapi.routing import APIRoute

    def _alle(dependant: Any) -> list[Any]:
        return [d for sub in dependant.dependencies for d in [sub.call, *_alle(sub)]]

    for route in app.routes:
        if isinstance(route, APIRoute):
            for afh in _alle(route.dependant):
                if getattr(afh, "__name__", "") == "permission_checker":
                    app.dependency_overrides[afh] = lambda: 1

    return app


# ---------------------------------------------------------------------------
# Test: approved flow proceeds to ActivePieces
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApprovedFlowProceedsToActivePieces:
    def test_approved_flow_calls_service_execute(self):
        """Council APPROVED verdict → service.execute_flow() is called."""
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=_make_decision(DecisionVerdict.APPROVED))
        service = MagicMock()
        service.db = AsyncMock()
        service.execute_flow = AsyncMock(return_value={"execution_id": "exec_abc"})

        app = _make_app(council, service)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.post("/api/v1/focus-builder/flows/42/execute", json={"key": "value"})

        assert resp.status_code == 202
        assert resp.json()["execution_id"] == "exec_abc"
        council.deliberate.assert_awaited_once()
        service.execute_flow.assert_awaited_once()

    def test_approved_flow_sends_only_input_keys_to_council(self):
        """action_params must not include input VALUES — only KEYS (PII guard)."""
        captured_proposal = {}

        async def capture_deliberate(proposal: Any) -> MagicMock:
            captured_proposal["proposal"] = proposal
            return _make_decision(DecisionVerdict.APPROVED)

        council = MagicMock()
        council.deliberate = capture_deliberate
        service = MagicMock()
        service.db = AsyncMock()
        service.execute_flow = AsyncMock(return_value={"execution_id": "exec_abc"})

        app = _make_app(council, service)
        client = TestClient(app)

        client.post(
            "/api/v1/focus-builder/flows/99/execute",
            json={"email": "user@example.com", "amount": "1000"},
        )

        proposal = captured_proposal["proposal"]
        assert proposal.action_type == "focus_builder.execute_flow"
        params_str = str(proposal.action_params)
        assert "user@example.com" not in params_str
        assert "1000" not in params_str
        assert "email" in proposal.action_params["input_keys"]
        assert "amount" in proposal.action_params["input_keys"]


# ---------------------------------------------------------------------------
# Test: blocked flow raises 403
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBlockedFlowRaises403:
    def test_blocked_verdict_returns_403(self):
        """Council BLOCKED verdict → 403 with FLOW_BLOCKED_BY_COUNCIL code."""
        council = MagicMock()
        council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.BLOCKED, "Security policy violation")
        )
        service = MagicMock()
        service.db = AsyncMock()
        service.execute_flow = AsyncMock()

        app = _make_app(council, service)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/focus-builder/flows/42/execute", json={})

        assert resp.status_code == 403
        detail = resp.json()["detail"]  # FastAPI wraps detail in {"detail": ...}
        assert detail["code"] == "FLOW_BLOCKED_BY_COUNCIL"
        assert "Security policy violation" in detail["reason"]

    def test_blocked_flow_does_not_call_service_execute(self):
        """When Council blocks, ActivePieces execute must NOT be called."""
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=_make_decision(DecisionVerdict.BLOCKED))
        service = MagicMock()
        service.db = AsyncMock()
        service.execute_flow = AsyncMock()

        app = _make_app(council, service)
        client = TestClient(app, raise_server_exceptions=False)

        client.post("/api/v1/focus-builder/flows/42/execute", json={})

        service.execute_flow.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: HITL_REQUIRED verdict
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHITLRequiredVerdict:
    def test_hitl_required_blocks_execution(self):
        """HITL_REQUIRED also returns 403 — execution waits for human approval."""
        council = MagicMock()
        council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.HITL_REQUIRED, "Human review required")
        )
        service = MagicMock()
        service.db = AsyncMock()
        service.execute_flow = AsyncMock()

        app = _make_app(council, service)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/focus-builder/flows/55/execute", json={})

        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert "decision_id" in detail
        assert detail["hitl_request_id"] is None, (
            "focus_builder.execute_flow is geen geregistreerde tool -- geen ticket "
            "mogelijk (ADR-036 OP-90), maar dat mag niet crashen: additieve sleutel, "
            "waarde None."
        )
        service.execute_flow.assert_not_awaited()

    def test_hitl_required_creates_a_ticket_when_the_tool_is_known(self) -> None:
        """ADR-036 OP-167 (sprint dag 2): een HITL_REQUIRED-verdict maakt nu een echt
        goedkeuringsticket aan, en de ref bereikt de 403-body onder `hitl_request_id`."""
        from unittest.mock import patch

        council = MagicMock()
        council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.HITL_REQUIRED, "Human review required")
        )
        service = MagicMock()
        service.db = AsyncMock()
        service.execute_flow = AsyncMock()

        fake_repo = AsyncMock()
        fake_repo.create_hitl_request = AsyncMock(return_value="TICKET-REF-FLOW")

        app = _make_app(council, service)
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "src.core.tool_broker.hitl_repository.HITLTicketRepository",
            return_value=fake_repo,
        ):
            resp = client.post("/api/v1/focus-builder/flows/55/execute", json={})

        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["hitl_request_id"] == "TICKET-REF-FLOW"
        fake_repo.create_hitl_request.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test: Council exception returns 500
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCouncilErrorReturns500:
    def test_council_runtime_error_returns_500(self):
        """When council.deliberate() throws, endpoint returns 500 — no silent fail."""
        council = MagicMock()
        council.deliberate = AsyncMock(side_effect=RuntimeError("Redis connection lost"))
        service = MagicMock()
        service.db = AsyncMock()
        service.execute_flow = AsyncMock()

        app = _make_app(council, service)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/focus-builder/flows/42/execute", json={})

        assert resp.status_code == 500
        # create_error_response() wraps under {"error": {...}}, FastAPI adds {"detail": ...}
        detail = resp.json()["detail"]
        assert detail["error"]["code"] == "COUNCIL_UNAVAILABLE"
        service.execute_flow.assert_not_awaited()
