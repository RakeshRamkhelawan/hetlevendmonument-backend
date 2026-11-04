"""Tests for POST /api/v1/copilot/proactive/{signal_id}/respond."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.core.copilot.api.turn_endpoint import router as turn_router
from src.core.copilot.dependencies import get_copilot_service
from src.core.copilot.service import CopilotService


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    # Mock tenant middleware
    from src.core.middleware.tenant_context import set_tenant_id

    @app.middleware("http")
    async def add_tenant_state(request: Request, call_next: Any) -> Any:
        set_tenant_id(1)
        request.state.tenant_id = 1
        request.state.user_id = 7
        return await call_next(request)

    # Mock auth dependency
    from src.core.auth.dependencies import get_current_user

    class FakeUser:
        id = 7
        tenant_id = 1
        roles = ["admin"]
        is_superuser = False

    app.dependency_overrides[get_current_user] = lambda: FakeUser()

    # Build real CopilotService with mocked council/llm/proposal_builder
    council = AsyncMock()
    llm_handler = AsyncMock()
    proposal_builder = AsyncMock()
    audit_writer = AsyncMock()
    service = CopilotService(
        council=council,
        llm_handler=llm_handler,
        proposal_builder=proposal_builder,
        audit_writer=audit_writer,
    )
    app.dependency_overrides[get_copilot_service] = lambda: service

    # SEC-010: the endpoint enforces CSRF; override it to a no-op so the happy-path
    # tests exercise the handler. A dedicated test below removes the override to
    # assert the 403.
    from src.core.api.auth.dependencies import validate_csrf_token

    app.dependency_overrides[validate_csrf_token] = lambda: None

    app.include_router(turn_router, prefix="/api/v1/copilot")

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_respond_with_confirm_returns_accepted_true(client: TestClient) -> None:
    signal_id = "00000000-0000-0000-0000-000000000001"
    response = client.post(
        f"/api/v1/copilot/proactive/{signal_id}/respond",
        json={"action_type": "confirm", "params": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["resulting_action"] == "confirm"
    assert "confirm" in body["message"]
    assert body["signal_id"] == signal_id


def test_respond_with_unknown_action_returns_422(client: TestClient) -> None:
    signal_id = "00000000-0000-0000-0000-000000000001"
    response = client.post(
        f"/api/v1/copilot/proactive/{signal_id}/respond",
        json={"action_type": "explode", "params": {}},
    )
    assert response.status_code == 422


def test_respond_without_jwt_returns_401(client: TestClient, app: FastAPI) -> None:
    # Replace auth override with one that raises 401
    from fastapi import HTTPException
    from src.core.auth.dependencies import get_current_user

    async def _unauthorized():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _unauthorized

    signal_id = "00000000-0000-0000-0000-000000000001"
    response = client.post(
        f"/api/v1/copilot/proactive/{signal_id}/respond",
        json={"action_type": "confirm", "params": {}},
    )
    assert response.status_code == 401


def test_respond_without_csrf_token_returns_403(client: TestClient, app: FastAPI) -> None:
    # Remove the no-op CSRF override so the real Depends(validate_csrf_token) runs.
    from src.core.api.auth.dependencies import validate_csrf_token

    app.dependency_overrides.pop(validate_csrf_token, None)

    signal_id = "00000000-0000-0000-0000-000000000001"
    response = client.post(
        f"/api/v1/copilot/proactive/{signal_id}/respond",
        json={"action_type": "confirm", "params": {}},
    )
    assert response.status_code == 403


def test_respond_when_audit_fails_still_returns_200(client: TestClient, app: FastAPI) -> None:
    # Replace the service with one whose audit writer raises
    from src.core.copilot.dependencies import get_copilot_service

    class RaisingAudit:
        async def log_user_response(self, **kwargs: Any) -> None:
            raise RuntimeError("audit db down")

    council = AsyncMock()
    llm_handler = AsyncMock()
    proposal_builder = AsyncMock()
    service = CopilotService(
        council=council,
        llm_handler=llm_handler,
        proposal_builder=proposal_builder,
        audit_writer=RaisingAudit(),
    )
    app.dependency_overrides[get_copilot_service] = lambda: service

    signal_id = "00000000-0000-0000-0000-000000000001"
    response = client.post(
        f"/api/v1/copilot/proactive/{signal_id}/respond",
        json={"action_type": "confirm", "params": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
