"""E2E integration test: FocusBuilder execute_flow -> AgentCouncil governance gate.

Behavioral: flow execution is blocked by the Council before reaching ActivePieces.
Approved flows proceed to service.execute_flow().
Council errors surface as 500 — no silent failures.
"""

from __future__ import annotations

import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.core.copilot.council.types import DecisionVerdict


# ---------------------------------------------------------------------------
# Shared app factory (mirrors test_focus_builder_council_gate pattern)
# ---------------------------------------------------------------------------


def _make_decision(verdict: DecisionVerdict, explanation: str = "") -> MagicMock:
    decision = MagicMock()
    decision.verdict = verdict
    decision.explanation_for_user = explanation
    decision.decision_id = uuid4()
    return decision


def _make_app(council_mock: MagicMock, service_mock: MagicMock) -> FastAPI:
    from src.core.api.v1.focus_builder.router import router, get_focus_builder_service
    from src.core.api.v1.focus_builder.dependencies import get_focus_builder_council
    from src.core.auth.auth_service import UserResponse
    from src.core.auth.dependencies import get_current_user_dependency
    from src.core.middleware.tenant_context import set_tenant_id
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    app = FastAPI()

    @app.middleware("http")
    async def add_tenant(request: Request, call_next: Any) -> Any:
        set_tenant_id(10)
        return await call_next(request)

    no_op_limiter = Limiter(key_func=get_remote_address, default_limits=[])
    app.state.limiter = no_op_limiter
    app.include_router(router, prefix="/api/v1")

    mock_user = UserResponse(id=1, email="e2e@example.com", tenant_id=10)
    app.dependency_overrides[get_current_user_dependency] = lambda: mock_user
    app.dependency_overrides[get_focus_builder_service] = lambda: service_mock
    app.dependency_overrides[get_focus_builder_council] = lambda: council_mock
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
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFocusBuilderCouncilE2E:
    def test_approved_flow_reaches_activepieces(self):
        """Full path: Council APPROVED -> execute_flow called -> 202 returned."""
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=_make_decision(DecisionVerdict.APPROVED))
        service = MagicMock()
        service.db = MagicMock()
        service.execute_flow = AsyncMock(return_value={"execution_id": "ap_e2e_001"})

        client = TestClient(_make_app(council, service), raise_server_exceptions=True)
        resp = client.post(
            "/api/v1/focus-builder/flows/1/execute",
            json={"trigger_input": "start"},
        )

        assert resp.status_code == 202
        assert resp.json()["execution_id"] == "ap_e2e_001"
        council.deliberate.assert_awaited_once()
        service.execute_flow.assert_awaited_once_with(1, {"trigger_input": "start"})

    def test_blocked_flow_never_reaches_activepieces(self):
        """Council BLOCKED -> 403 returned -> service.execute_flow not called."""
        council = MagicMock()
        council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.BLOCKED, "Compliance violation")
        )
        service = MagicMock()
        service.db = MagicMock()
        service.execute_flow = AsyncMock()

        client = TestClient(_make_app(council, service), raise_server_exceptions=False)
        resp = client.post("/api/v1/focus-builder/flows/2/execute", json={})

        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "FLOW_BLOCKED_BY_COUNCIL"
        service.execute_flow.assert_not_awaited()

    def test_council_receives_action_type_focus_builder_execute_flow(self):
        """Proposal submitted to Council has correct action_type."""
        captured: dict[str, Any] = {}

        async def capture(proposal: Any) -> MagicMock:
            captured["proposal"] = proposal
            return _make_decision(DecisionVerdict.APPROVED)

        council = MagicMock()
        council.deliberate = capture
        service = MagicMock()
        service.db = MagicMock()
        service.execute_flow = AsyncMock(return_value={"execution_id": "x"})

        client = TestClient(_make_app(council, service))
        client.post("/api/v1/focus-builder/flows/7/execute", json={"amount": "100"})

        proposal = captured["proposal"]
        assert proposal.action_type == "focus_builder.execute_flow"
        assert proposal.action_params["flow_id"] == "7"
        # PII guard: amount value must not appear in params
        assert "100" not in str(proposal.action_params)

    def test_hitl_required_blocks_execution_without_human_approval(self):
        """HITL_REQUIRED -> 403 blocking flow until human approves via HITL ticket."""
        council = MagicMock()
        council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.HITL_REQUIRED, "Requires human sign-off")
        )
        service = MagicMock()
        service.db = MagicMock()
        service.execute_flow = AsyncMock()

        client = TestClient(_make_app(council, service), raise_server_exceptions=False)
        resp = client.post("/api/v1/focus-builder/flows/9/execute", json={})

        assert resp.status_code == 403
        service.execute_flow.assert_not_awaited()
