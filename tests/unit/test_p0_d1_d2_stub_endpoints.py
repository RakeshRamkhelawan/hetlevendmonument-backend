"""
AUDIT-P0-D1: /rag/search and /rag/ask return mock data (200) instead of HTTP 501.
AUDIT-P0-D2: WorkflowService._execute_step() returns status='completed' stub.

RED PHASE OUTPUT (2026-05-28):
  test_rag_search_returns_501: AssertionError: assert 200 == 501
  test_rag_ask_returns_501: AssertionError: assert 200 == 501
  test_execute_step_not_completed: AssertionError: assert 'completed' != 'completed'
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_rag_client() -> TestClient:
    """Build a minimal FastAPI test app with the RAG router and auth overrides."""
    from src.core.api.rag_endpoints import router as rag_router
    from src.core.auth.dependencies import get_current_user_dependency as get_current_user
    from src.core.middleware.tenant_context import require_tenant_id

    app = FastAPI()
    app.include_router(rag_router)

    mock_user = MagicMock()
    mock_user.email = "test@example.com"
    mock_user.id = 1

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[require_tenant_id] = lambda: 42

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.unit
class TestRagStubEndpoints:
    """AUDIT-P0-D1: RAG stub endpoints must return HTTP 501, not mock data."""

    def test_rag_search_returns_501_not_mock_data(self):
        """
        RED: POST /api/v1/rag/search currently returns 200 with mock results.
        After fix: must return 501 Not Implemented.
        Root cause: stub returns mock_results instead of raising HTTPException(501).
        """
        client = _make_rag_client()
        response = client.post(
            "/api/v1/rag/search",
            json={"query": "test query"},
        )
        assert response.status_code == 501, (
            f"AUDIT-P0-D1: /rag/search returns mock data ({response.status_code}) "
            "instead of 501 Not Implemented"
        )

    def test_rag_ask_returns_501_not_mock_answer(self):
        """
        RED: POST /api/v1/rag/ask currently returns 200 with a mock answer.
        After fix: must return 501 Not Implemented.
        Root cause: stub returns mock_answer instead of raising HTTPException(501).
        """
        client = _make_rag_client()
        response = client.post(
            "/api/v1/rag/ask",
            json={"question": "What is the company policy?"},
        )
        assert response.status_code == 501, (
            f"AUDIT-P0-D1: /rag/ask returns mock answer ({response.status_code}) "
            "instead of 501 Not Implemented"
        )

    def test_rag_reindex_returns_501(self):
        """
        MINOR-M3: POST /api/v1/rag/reindex must return 501 Not Implemented.
        The reindex endpoint is a stub -- actual reindexing is post-MVP.
        """
        client = _make_rag_client()
        response = client.post(
            "/api/v1/rag/reindex",
            json={},
        )
        assert response.status_code == 501, (
            "AUDIT-P0-D1: /rag/reindex must return 501 Not Implemented"
        )


@pytest.mark.unit
class TestWorkflowStub:
    """AUDIT-P0-D2: WorkflowService._execute_step() must not return 'completed'."""

    @pytest.mark.asyncio
    async def test_execute_step_not_completed(self):
        """
        RED: _execute_step() currently returns status='completed' for all step types.
        After fix: must return status='not_implemented'.
        Root cause: stub return value does not reflect actual execution state.
        """
        from src.domains.workflows.models import WorkflowStep
        from src.domains.workflows.services import WorkflowService

        service = WorkflowService()
        step = WorkflowStep(
            id="step-001",
            name="send_email",
            step_type="notification",
            order=0,
        )

        result = await service._execute_step(step)

        assert result.get("status") != "completed", (
            "AUDIT-P0-D2: _execute_step returns 'completed' stub -- "
            "workflows silently succeed without executing any real action"
        )
