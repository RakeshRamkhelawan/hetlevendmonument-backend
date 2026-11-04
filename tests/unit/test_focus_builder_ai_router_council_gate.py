"""ADR-036 OP-167 (HITL-ticket-volledigheid sprint dag 2): HITL-ticketaanmaak op de
ai_router.py-routes (`/ai/suggest`, `/ai/generate`).

Deze twee routes waren de ENIGE twee van de negen `require_council_approval`-aanroepers
die vooraf GEEN databasesessie in scope hadden (bevestigd via impact-analyse in de
sprint-opstarten-brief) -- `suggest_nodes` kreeg daarom een nieuwe
`service: FocusBuilderService = Depends(get_focus_builder_service)`-dependency erbij
(puur voor `.db`), en `generate_flow_ai` hergebruikt de `service`-dependency die het al
had. Zonder een test die deze twee routes daadwerkelijk door een TestClient stuurt, blijft
de nieuwe bedrading ongetest -- exact het risico dat een onafhankelijke Gate-2-review
aanwees.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.core.copilot.council.types import DecisionVerdict


def _make_decision(verdict: DecisionVerdict, explanation: str = "Test explanation") -> MagicMock:
    decision = MagicMock()
    decision.verdict = verdict
    decision.explanation_for_user = explanation
    decision.decision_id = uuid4()
    return decision


def _make_app(council_mock: MagicMock, service_mock: MagicMock) -> FastAPI:
    """Minimale FastAPI-app met de focus-builder-router + gemockte dependencies."""
    from src.core.api.v1.focus_builder.router import router, get_focus_builder_service
    from src.core.api.v1.focus_builder.dependencies import get_focus_builder_council
    from src.core.auth.dependencies import get_current_user_dependency
    from src.core.auth.auth_service import UserResponse
    from src.core.middleware.rate_limiter import get_limiter
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    app = FastAPI()

    from src.core.middleware.tenant_context import set_tenant_id

    @app.middleware("http")
    async def add_tenant(request: Request, call_next: Any) -> Any:
        set_tenant_id(10)
        return await call_next(request)

    no_op_limiter = Limiter(key_func=get_remote_address, default_limits=[])
    app.state.limiter = no_op_limiter

    app.include_router(router, prefix="/api/v1")

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

    return app


@pytest.mark.unit
class TestAiSuggestHitlTicket:
    """`/ai/suggest`: had voor deze sprint HELEMAAL geen databasesessie in scope."""

    def test_hitl_required_creates_a_ticket_via_the_new_service_dependency(self) -> None:
        council = MagicMock()
        council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.HITL_REQUIRED, "Human review required")
        )
        service = MagicMock()
        service.db = AsyncMock()

        fake_repo = AsyncMock()
        fake_repo.create_hitl_request = AsyncMock(return_value="TICKET-REF-SUGGEST")

        app = _make_app(council, service)
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "src.core.tool_broker.hitl_repository.HITLTicketRepository",
            return_value=fake_repo,
        ):
            resp = client.post(
                "/api/v1/focus-builder/ai/suggest",
                json={"prompt": "add a webhook node"},
            )

        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["hitl_request_id"] == "TICKET-REF-SUGGEST"
        fake_repo.create_hitl_request.assert_awaited_once()
        kwargs = fake_repo.create_hitl_request.await_args.kwargs
        assert kwargs["action_type"] == "focus_builder.ai_suggest"

    def test_approved_verdict_never_attempts_a_ticket(self) -> None:
        council = MagicMock()
        council.deliberate = AsyncMock(return_value=_make_decision(DecisionVerdict.APPROVED))
        service = MagicMock()
        service.db = AsyncMock()

        app = _make_app(council, service)
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "src.core.tool_broker.hitl_repository.HITLTicketRepository",
        ) as repo_cls:
            client.post(
                "/api/v1/focus-builder/ai/suggest",
                json={"prompt": "add a webhook node"},
            )

        repo_cls.assert_not_called()


@pytest.mark.unit
class TestAiGenerateHitlTicket:
    """`/ai/generate`: had al een `service`-dependency, maar gaf `db` niet door aan de
    poort -- deze test bewijst dat de bestaande dependency nu daadwerkelijk wordt
    gebruikt voor de HITL-ticketaanmaak."""

    def test_hitl_required_creates_a_ticket_via_the_existing_service_dependency(self) -> None:
        council = MagicMock()
        council.deliberate = AsyncMock(
            return_value=_make_decision(DecisionVerdict.HITL_REQUIRED, "Human review required")
        )
        service = MagicMock()
        service.db = AsyncMock()

        fake_repo = AsyncMock()
        fake_repo.create_hitl_request = AsyncMock(return_value="TICKET-REF-GENERATE")

        app = _make_app(council, service)
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "src.core.tool_broker.hitl_repository.HITLTicketRepository",
            return_value=fake_repo,
        ):
            resp = client.post(
                "/api/v1/focus-builder/ai/generate",
                json={"prompt": "generate an onboarding flow"},
            )

        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["hitl_request_id"] == "TICKET-REF-GENERATE"
        fake_repo.create_hitl_request.assert_awaited_once()
        kwargs = fake_repo.create_hitl_request.await_args.kwargs
        assert kwargs["action_type"] == "focus_builder.ai_generate"
