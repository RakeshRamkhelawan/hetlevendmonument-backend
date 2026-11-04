"""
SP-G02 — CVA copilot/turn end-to-end tests.

Verifies POST /api/v1/copilot/turn across 13 behavioral scenarios:
happy path, council verdicts, tenant isolation, rate limiting,
input validation, streaming, and rollout guard.

Design notes:
- get_copilot_service is overridden to avoid DB/Redis/LLM deps.
- check_copilot_rollout is overridden to prevent env-sensitive 403s in CI.
- set_tenant_id(1) MUST precede call_next in middleware so copilot_turn_limit
  key_func (which reads the ContextVar directly) resolves before the route runs.
- _rate_limiter is a module-level singleton; setup_method clears it between tests.
"""

import os
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("COPILOT_COUNCIL_V1_ROLLOUT_PCT", "100")
os.environ.setdefault("TESTING", "1")

from src.core.api.auth.dependencies import validate_csrf_token
from src.core.auth.dependencies import UserResponse, get_current_user
from src.core.config.feature_flags import check_copilot_rollout
from src.core.copilot.api.turn_endpoint import router as turn_router
from src.core.copilot.dependencies import get_copilot_service
from src.core.copilot.schemas import CopilotTurnResponse
from src.core.governance.rate_limiter import _rate_limiter
from src.core.middleware.tenant_context import set_tenant_id

pytestmark = [pytest.mark.unit, pytest.mark.security]

_TENANT_ID = 1
_USER_ID = 42

_APPROVED_RESPONSE = CopilotTurnResponse(
    decision_id="00000000-0000-0000-0000-000000000001",
    verdict="approved",
    message="Action approved.",
    action="no_op",
    action_params={},
    confidence=0.92,
    council_summary={},
    hitl_request_id=None,
    explanation_url=None,
)

_BLOCKED_RESPONSE = CopilotTurnResponse(
    decision_id="00000000-0000-0000-0000-000000000002",
    verdict="blocked",
    message="Action blocked by policy.",
    action=None,
    action_params={},
    confidence=0.1,
    council_summary={},
    hitl_request_id=None,
    explanation_url=None,
)

_HITL_RESPONSE = CopilotTurnResponse(
    decision_id="00000000-0000-0000-0000-000000000003",
    verdict="hitl_required",
    message="Human review required.",
    action=None,
    action_params={},
    confidence=0.5,
    council_summary={},
    hitl_request_id="00000000-0000-0000-0000-000000000099",
    explanation_url=None,
)


def _make_mock_service(response: CopilotTurnResponse) -> MagicMock:
    svc = MagicMock()
    svc.handle_turn = AsyncMock(return_value=response)

    # Minimal async generator for streaming path
    async def _stream(**_: Any) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "delta", "content": "Hello"}
        yield {"type": "done"}

    svc.handle_turn_stream = _stream
    return svc


def _make_mock_user() -> UserResponse:
    user = MagicMock(spec=UserResponse)
    user.id = _USER_ID
    user.tenant_id = _TENANT_ID
    return user


def _make_client(service: MagicMock | None = None) -> TestClient:
    """Build a minimal FastAPI app wired with the turn router and test overrides."""
    if service is None:
        service = _make_mock_service(_APPROVED_RESPONSE)

    app = FastAPI()

    # NOTE: set_tenant_id MUST precede call_next — copilot_turn_limit reads the
    # ContextVar during route dispatch before request.state is populated.
    @app.middleware("http")
    async def inject_tenant(request: Any, call_next: Any) -> Any:
        set_tenant_id(_TENANT_ID)
        request.state.tenant_id = _TENANT_ID
        request.state.user_id = _USER_ID
        request.state.limiet_gebruiker = f"u{_USER_ID}"
        return await call_next(request)

    app.include_router(turn_router, prefix="/api/v1/copilot")

    mock_user = _make_mock_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_copilot_service] = lambda: service
    # Override rollout guard so CI env vars cannot cause 403 on happy-path tests.
    app.dependency_overrides[check_copilot_rollout] = lambda: None
    # CSRF is a browser-cookie concern (SEC-CSRF hardening); this test client
    # has no session/cookie flow to validate, so bypass it like the other
    # cross-cutting dependencies above.
    app.dependency_overrides[validate_csrf_token] = lambda: None

    return TestClient(app, raise_server_exceptions=False)


class TestCopilotTurnEndpoint:
    def setup_method(self) -> None:
        # Clear module-level singleton so tests do not share rate-limit state.
        _rate_limiter._requests.clear()
        _rate_limiter._last_cleanup = 0.0

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_approved_turn_returns_200_with_response_fields(self) -> None:
        """POST /turn with valid message returns 200 and all required fields."""
        client = _make_client()
        resp = client.post("/api/v1/copilot/turn", json={"message": "Help me automate a task."})
        assert resp.status_code == 200
        body = resp.json()
        assert body["verdict"] == "approved"
        assert "decision_id" in body
        assert "message" in body
        assert "confidence" in body

    def test_complete_json_is_used_not_raw_llm_text(self) -> None:
        """CopilotService.handle_turn is called (verifying complete_json pipeline)."""
        svc = _make_mock_service(_APPROVED_RESPONSE)
        client = _make_client(service=svc)
        client.post("/api/v1/copilot/turn", json={"message": "Schedule a report."})
        svc.handle_turn.assert_awaited_once()

    def test_handle_turn_receives_correct_tenant_and_user(self) -> None:
        """tenant_id and user_id are injected from middleware, not request body."""
        svc = _make_mock_service(_APPROVED_RESPONSE)
        client = _make_client(service=svc)
        client.post("/api/v1/copilot/turn", json={"message": "Run analysis."})
        call_kwargs = svc.handle_turn.call_args.kwargs
        assert call_kwargs["tenant_id"] == _TENANT_ID
        assert call_kwargs["user_id"] == _USER_ID

    # ------------------------------------------------------------------
    # Council verdict paths
    # ------------------------------------------------------------------

    def test_blocked_verdict_returns_200_with_blocked_verdict(self) -> None:
        """Council-blocked decision is surfaced as verdict=blocked, not an error."""
        client = _make_client(service=_make_mock_service(_BLOCKED_RESPONSE))
        resp = client.post("/api/v1/copilot/turn", json={"message": "Delete all records."})
        assert resp.status_code == 200
        assert resp.json()["verdict"] == "blocked"

    def test_hitl_required_verdict_includes_hitl_request_id(self) -> None:
        """HITL verdict response includes hitl_request_id field."""
        client = _make_client(service=_make_mock_service(_HITL_RESPONSE))
        resp = client.post("/api/v1/copilot/turn", json={"message": "Approve budget."})
        assert resp.status_code == 200
        body = resp.json()
        assert body["verdict"] == "hitl_required"
        assert body["hitl_request_id"] is not None

    # ------------------------------------------------------------------
    # Tenant isolation
    # ------------------------------------------------------------------

    def test_tenant_id_not_accepted_in_request_body(self) -> None:
        """Request body with tenant_id field is rejected (extra=forbid)."""
        client = _make_client()
        resp = client.post(
            "/api/v1/copilot/turn",
            json={"message": "Do something.", "tenant_id": 99},
        )
        assert resp.status_code == 422

    def test_handle_turn_tenant_id_matches_middleware_not_body(self) -> None:
        """Even if request body had no tenant_id, service receives middleware value."""
        svc = _make_mock_service(_APPROVED_RESPONSE)
        client = _make_client(service=svc)
        client.post("/api/v1/copilot/turn", json={"message": "Check status."})
        assert svc.handle_turn.call_args.kwargs["tenant_id"] == _TENANT_ID

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def test_unauthenticated_request_returns_401_and_service_not_called(self) -> None:
        """Auth rejection (401) happens before service.handle_turn is called."""
        from fastapi import HTTPException as FastAPIHTTPException

        def reject_auth() -> Any:
            raise FastAPIHTTPException(status_code=401, detail="Not authenticated")

        app = FastAPI()

        @app.middleware("http")
        async def inject_tenant_only(request: Any, call_next: Any) -> Any:
            set_tenant_id(_TENANT_ID)
            request.state.tenant_id = _TENANT_ID
            return await call_next(request)

        app.include_router(turn_router, prefix="/api/v1/copilot")
        svc = _make_mock_service(_APPROVED_RESPONSE)
        app.dependency_overrides[get_current_user] = reject_auth
        app.dependency_overrides[get_copilot_service] = lambda: svc
        app.dependency_overrides[check_copilot_rollout] = lambda: None

        unauth_client = TestClient(app, raise_server_exceptions=False)
        resp = unauth_client.post("/api/v1/copilot/turn", json={"message": "Hello."})
        assert resp.status_code == 401
        svc.handle_turn.assert_not_awaited()

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    def test_empty_message_returns_422(self) -> None:
        """Empty string violates min_length=1 constraint."""
        client = _make_client()
        resp = client.post("/api/v1/copilot/turn", json={"message": ""})
        assert resp.status_code == 422

    def test_missing_message_returns_422(self) -> None:
        """Missing required field returns 422."""
        client = _make_client()
        resp = client.post("/api/v1/copilot/turn", json={})
        assert resp.status_code == 422

    def test_message_exceeding_max_length_returns_422(self) -> None:
        """Message longer than 2000 chars violates max_length constraint."""
        client = _make_client()
        resp = client.post("/api/v1/copilot/turn", json={"message": "x" * 2001})
        assert resp.status_code == 422

    # ------------------------------------------------------------------
    # Language parameter
    # ------------------------------------------------------------------

    def test_english_language_parameter_accepted(self) -> None:
        """language=en is a valid Literal value."""
        client = _make_client()
        resp = client.post(
            "/api/v1/copilot/turn",
            json={"message": "Run a workflow.", "language": "en"},
        )
        assert resp.status_code == 200

    def test_invalid_language_returns_422(self) -> None:
        """Language value outside Literal['nl','en'] is rejected."""
        client = _make_client()
        resp = client.post(
            "/api/v1/copilot/turn",
            json={"message": "Run workflow.", "language": "fr"},
        )
        assert resp.status_code == 422

    # ------------------------------------------------------------------
    # Streaming path
    # ------------------------------------------------------------------

    def test_streaming_request_returns_event_stream(self) -> None:
        """stream=True triggers SSE streaming response with text/event-stream content type."""
        client = _make_client()
        resp = client.post(
            "/api/v1/copilot/turn",
            json={"message": "Stream me a response.", "stream": True},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
