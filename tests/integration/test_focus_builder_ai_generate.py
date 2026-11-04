"""
SP-G04 Integration Tests: Focus Builder AI Generate End-to-End

Tests verify the full user journey through the async stack:
  Authenticated request -> Council gate -> LLM complete_json() -> Response wrapper

Uses httpx.AsyncClient with ASGITransport to avoid Windows ProactorEventLoop
conflicts that plague sync TestClient + asyncpg.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from slowapi import Limiter

from src.core.api.v1.focus_builder.dependencies import get_focus_builder_council
from src.core.api.v1.focus_builder.shared import get_focus_builder_service
from src.core.copilot.council.types import DecisionVerdict


@pytest.fixture(autouse=True, scope="module")
def _patch_limiter_for_integration():
    """Disable rate limiting for all tests in this module."""
    original = Limiter._Limiter__evaluate_limits

    def _no_op_evaluate(self, request, endpoint, limits):
        request.state.view_rate_limit = None

    Limiter._Limiter__evaluate_limits = _no_op_evaluate
    yield
    Limiter._Limiter__evaluate_limits = original


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_council(verdict: DecisionVerdict, explanation: str = "Test") -> MagicMock:
    council = MagicMock()
    decision = MagicMock()
    decision.verdict = verdict
    decision.explanation_for_user = explanation
    decision.decision_id = "test-decision-id"
    council.deliberate = AsyncMock(return_value=decision)
    return council


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFocusBuilderAIGenerateIntegration:
    """End-to-end tests for POST /api/v1/focus-builder/ai/generate"""

    @pytest.fixture(autouse=True)
    def _mock_focus_builder_service(self, integration_app):
        """Override get_focus_builder_service so ActivePiecesClient is never instantiated."""
        integration_app.dependency_overrides[get_focus_builder_service] = lambda: MagicMock()
        yield
        integration_app.dependency_overrides.pop(get_focus_builder_service, None)

    @pytest.mark.asyncio
    async def test_happy_path_returns_workflow_graph(
        self, integration_app, integration_client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        """
        User behavior: Authenticated user sends a natural-language prompt
        and receives a structured ReactFlow graph wrapped in success envelope.
        """
        integration_app.dependency_overrides[get_focus_builder_council] = lambda: _make_council(
            DecisionVerdict.APPROVED
        )

        with patch("src.domains.flows.agentic_service.AgenticFlowService") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.generate_flow_from_prompt = AsyncMock(
                return_value={
                    "success": True,
                    "data": {
                        "react_flow_graph": {
                            "nodes": [
                                {
                                    "id": "trigger_1",
                                    "type": "trigger",
                                    "position": {"x": 250, "y": 200},
                                    "data": {"label": "Start"},
                                },
                                {
                                    "id": "action_1",
                                    "type": "action",
                                    "position": {"x": 500, "y": 200},
                                    "data": {"label": "Send Email"},
                                },
                            ],
                            "edges": [
                                {"id": "e1", "source": "trigger_1", "target": "action_1"},
                            ],
                        }
                    },
                }
            )
            mock_cls.return_value = mock_instance

            response = await integration_client.post(
                "/api/v1/focus-builder/ai/generate",
                json={"prompt": "Send an email when a form is submitted"},
                headers=admin_auth_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "data" in body
        graph = body["data"]["react_flow_graph"]
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 1
        assert graph["nodes"][0]["type"] == "trigger"

        # Verify service called with tenant_id from JWT context
        mock_instance.generate_flow_from_prompt.assert_awaited_once()
        call_kwargs = mock_instance.generate_flow_from_prompt.call_args.kwargs
        assert call_kwargs.get("tenant_id") == 1

        integration_app.dependency_overrides.pop(get_focus_builder_council, None)

    @pytest.mark.asyncio
    async def test_council_blocked_returns_403(
        self, integration_app, integration_client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        """
        User behavior: When Council returns BLOCKED, the user receives 403
        and generation is NOT attempted.
        """
        integration_app.dependency_overrides[get_focus_builder_council] = lambda: _make_council(
            DecisionVerdict.BLOCKED
        )

        with patch("src.domains.flows.agentic_service.AgenticFlowService") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.generate_flow_from_prompt = AsyncMock()
            mock_cls.return_value = mock_instance

            response = await integration_client.post(
                "/api/v1/focus-builder/ai/generate",
                json={"prompt": "Create a workflow"},
                headers=admin_auth_headers,
            )

        assert response.status_code == 403
        body = response.json()
        assert body["detail"]["code"] == "GOVERNANCE_BLOCKED"
        mock_instance.generate_flow_from_prompt.assert_not_awaited()

        integration_app.dependency_overrides.pop(get_focus_builder_council, None)

    @pytest.mark.asyncio
    async def test_hitl_required_returns_403(
        self, integration_app, integration_client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        """
        User behavior: When Council returns HITL_REQUIRED, the user receives 403
        with a decision_id for manual review.
        """
        integration_app.dependency_overrides[get_focus_builder_council] = lambda: _make_council(
            DecisionVerdict.HITL_REQUIRED
        )

        with patch("src.domains.flows.agentic_service.AgenticFlowService") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.generate_flow_from_prompt = AsyncMock()
            mock_cls.return_value = mock_instance

            response = await integration_client.post(
                "/api/v1/focus-builder/ai/generate",
                json={"prompt": "Create a workflow"},
                headers=admin_auth_headers,
            )

        assert response.status_code == 403
        body = response.json()
        assert "decision_id" in body["detail"]
        mock_instance.generate_flow_from_prompt.assert_not_awaited()

        integration_app.dependency_overrides.pop(get_focus_builder_council, None)

    @pytest.mark.asyncio
    async def test_llm_failure_returns_500(
        self, integration_app, integration_client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        """
        User behavior: When the LLM provider fails, the endpoint returns 500
        with a structured error code.
        """
        integration_app.dependency_overrides[get_focus_builder_council] = lambda: _make_council(
            DecisionVerdict.APPROVED
        )

        with patch("src.domains.flows.agentic_service.AgenticFlowService") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.generate_flow_from_prompt = AsyncMock(
                return_value={
                    "success": False,
                    "error": {
                        "code": "LLM_GENERATION_FAILED",
                        "message": "DeepSeek timeout",
                    },
                }
            )
            mock_cls.return_value = mock_instance

            response = await integration_client.post(
                "/api/v1/focus-builder/ai/generate",
                json={"prompt": "Create a workflow"},
                headers=admin_auth_headers,
            )

        assert response.status_code == 500
        body = response.json()
        assert body["detail"]["error"]["code"] == "LLM_GENERATION_FAILED"
        assert "DeepSeek timeout" in body["detail"]["error"]["message"]

        integration_app.dependency_overrides.pop(get_focus_builder_council, None)

    @pytest.mark.asyncio
    async def test_missing_prompt_returns_400(
        self, integration_app, integration_client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        """
        User behavior: Sending an empty body without 'prompt' returns 400.
        """
        integration_app.dependency_overrides[get_focus_builder_council] = lambda: _make_council(
            DecisionVerdict.APPROVED
        )

        response = await integration_client.post(
            "/api/v1/focus-builder/ai/generate",
            json={},
            headers=admin_auth_headers,
        )

        assert response.status_code == 400
        integration_app.dependency_overrides.pop(get_focus_builder_council, None)
