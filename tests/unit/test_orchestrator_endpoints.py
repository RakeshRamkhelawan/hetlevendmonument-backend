"""Tests voor orchestrator_endpoints.py -- SP-API-010 proxy stub (ADR-033).

Oude tests patchten OversightGate + ProductionWorkflowEngine die in SP-API-010
verwijderd zijn (verboden imports ADR-033). Vervangen door stub-gedrag tests.
"""

from unittest.mock import MagicMock

import pytest

from src.core.api.orchestrator_endpoints import TaskDelegationRequest, execute_multi_agent_task


@pytest.fixture
def mock_current_user():
    user = MagicMock()
    user.email = "tester@example.com"
    user.tenant_id = 42
    user.id = "user-1"
    return user


@pytest.fixture
def mock_response():
    resp = MagicMock()
    resp.headers = {}
    return resp


class TestOrchestratorEndpoints:
    @pytest.mark.asyncio
    async def test_multi_agent_task_returns_deprecated_status(
        self, mock_current_user, mock_response
    ):
        """SP-API-010 stub: POST /multi-agent retourneert status=deprecated."""
        result = await execute_multi_agent_task(
            request=TaskDelegationRequest(description="deploy app", type="deployment"),
            response=mock_response,
            current_user=mock_current_user,
        )
        assert result["status"] == "deprecated"

    @pytest.mark.asyncio
    async def test_multi_agent_task_sets_deprecation_header(self, mock_current_user, mock_response):
        """SP-API-010 stub: Deprecation + Sunset RFC headers worden gezet."""
        await execute_multi_agent_task(
            request=TaskDelegationRequest(description="deploy app", type="deployment"),
            response=mock_response,
            current_user=mock_current_user,
        )
        assert mock_response.headers["Deprecation"] == "true"
        assert "Sunset" in mock_response.headers

    @pytest.mark.asyncio
    async def test_multi_agent_task_message_references_sp_api_011(
        self, mock_current_user, mock_response
    ):
        """SP-API-010 stub: message verwijst naar SP-API-011 voor migratie."""
        result = await execute_multi_agent_task(
            request=TaskDelegationRequest(description="long task", type="task_management"),
            response=mock_response,
            current_user=mock_current_user,
        )
        assert "SP-API-011" in result["message"]

    @pytest.mark.asyncio
    async def test_multi_agent_task_echoes_type_for_client_compat(
        self, mock_current_user, mock_response
    ):
        """SP-API-010 stub: assigned_agent echoot request.type voor client-compatibiliteit."""
        result = await execute_multi_agent_task(
            request=TaskDelegationRequest(description="migrate db", type="database_migration"),
            response=mock_response,
            current_user=mock_current_user,
        )
        assert result["assigned_agent"] == "database_migration"
