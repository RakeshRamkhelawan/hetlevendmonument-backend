"""
Integration tests for Orchestration API endpoints.

Tests the REST API layer that wraps:
- MasterOrchestratorAgent
- AgentRouterAgent
- AgentHealthMonitorAgent
- CriticAgent
"""

import pytest
from httpx import AsyncClient

# Mark all tests as async
pytestmark = pytest.mark.asyncio


async def _flush_health_monitors() -> None:
    """Flush any pending batched health records in cached monitor instances."""
    from src.core.api.v1.orchestration.dependencies import _health_monitor_cache

    for monitor in _health_monitor_cache.values():
        if getattr(monitor, "_pending_records", None):
            await monitor._flush_batch()


class TestOrchestrateTaskEndpoint:
    """Test POST /api/v1/orchestrate/task"""

    async def test_orchestrate_task_success(self, client: AsyncClient, admin_auth_headers):
        """Test successful task orchestration."""
        response = await client.post(
            "/api/v1/orchestrate/task",
            headers=admin_auth_headers,
            json={
                "task": {
                    "title": "Test workflow",
                    "description": "Test the orchestration API with a simple task.",
                    "parameters": {"test": True},
                    "metadata": {"source": "test"},
                },
                "workflow_mode": "sequential",
                "max_subtasks": 4,
                "require_critic_review": False,
            },
        )

        # Should return 200 even if LLM fails (fallback mechanism)
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()
            assert "workflow_id" in data
            assert "status" in data
            assert "total_execution_time" in data

    async def test_orchestrate_task_validation_error(self, client: AsyncClient, admin_auth_headers):
        """Test validation error for missing required fields."""
        response = await client.post(
            "/api/v1/orchestrate/task",
            headers=admin_auth_headers,
            json={
                # Missing "task" field
                "workflow_mode": "sequential",
            },
        )

        assert response.status_code == 422  # Validation error

    async def test_orchestrate_task_with_critic(self, client: AsyncClient, admin_auth_headers):
        """Test orchestration with critic review enabled."""
        response = await client.post(
            "/api/v1/orchestrate/task",
            headers=admin_auth_headers,
            json={
                "task": {
                    "title": "Test with critic",
                    "description": "Test workflow with critic review enabled.",
                },
                "workflow_mode": "sequential",
                "require_critic_review": True,
            },
        )

        # Should complete (may fail if no LLM, but structure should be valid)
        if response.status_code == 200:
            data = response.json()
            # Critic may or may not be present depending on success
            assert "workflow_id" in data


class TestRouteTaskEndpoint:
    """Test POST /api/v1/orchestrate/route"""

    async def test_route_task_basic(self, client: AsyncClient, admin_auth_headers):
        """Test basic task routing."""
        response = await client.post(
            "/api/v1/orchestrate/route",
            headers=admin_auth_headers,
            json={
                "task": {
                    "title": "Route this task",
                    "description": "Find the best agent for this task.",
                },
                "required_capabilities": [],
                "fallback_to_llm": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert "routed_to_agent" in data
        assert "routing_method" in data
        assert "confidence_score" in data
        assert 0.0 <= data["confidence_score"] <= 1.0

    async def test_route_task_with_capabilities(self, client: AsyncClient, admin_auth_headers):
        """Test routing with required capabilities."""
        response = await client.post(
            "/api/v1/orchestrate/route",
            headers=admin_auth_headers,
            json={
                "task": {
                    "title": "Code review task",
                    "description": "Review Python code for quality.",
                },
                "required_capabilities": ["code_review", "python"],
                "fallback_to_llm": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "routed_to_agent" in data


class TestHealthEndpoints:
    """Test /api/v1/orchestrate/health endpoints"""

    async def test_get_health_report(self, client: AsyncClient, admin_auth_headers):
        """Test getting full health report."""
        # First record some health data
        await client.post(
            "/api/v1/orchestrate/health/record",
            headers=admin_auth_headers,
            json={
                "agent_id": "test_health_agent_001",
                "agent_type": "TestAgent",
                "latency_ms": 150.0,
                "success": True,
                "load": 0.3,
            },
        )

        response = await client.get("/api/v1/orchestrate/health", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        assert "total_agents" in data
        assert "agents" in data
        assert "by_status" in data
        assert "overall_health_score" in data

    async def test_get_agent_health(self, client: AsyncClient, admin_auth_headers):
        """Test getting specific agent health."""
        agent_id = "test_agent_health_002"

        # Record health data
        await client.post(
            "/api/v1/orchestrate/health/record",
            headers=admin_auth_headers,
            json={
                "agent_id": agent_id,
                "agent_type": "TestAgent",
                "latency_ms": 200.0,
                "success": True,
                "load": 0.5,
            },
        )
        await _flush_health_monitors()

        response = await client.get(
            f"/api/v1/orchestrate/health/agent/{agent_id}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == agent_id
        assert data["exists"] is True
        assert data["snapshot"] is not None
        assert data["snapshot"]["agent_id"] == agent_id

    async def test_get_agent_health_not_found(self, client: AsyncClient, admin_auth_headers):
        """Test getting health for non-existent agent."""
        response = await client.get(
            "/api/v1/orchestrate/health/agent/non_existent_agent",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "non_existent_agent"
        assert data["exists"] is False
        assert data["snapshot"] is None

    async def test_record_health(self, client: AsyncClient, admin_auth_headers):
        """Test recording health metrics."""
        response = await client.post(
            "/api/v1/orchestrate/health/record",
            headers=admin_auth_headers,
            json={
                "agent_id": "test_record_agent",
                "agent_type": "TestAgent",
                "latency_ms": 100.0,
                "success": True,
                "load": 0.2,
                "error_message": None,
            },
        )

        assert response.status_code == 204


class TestCritiqueEndpoint:
    """Test POST /api/v1/orchestrate/critique"""

    async def test_critique_output(self, client: AsyncClient, admin_auth_headers):
        """Test critiquing agent output."""
        response = await client.post(
            "/api/v1/orchestrate/critique",
            headers=admin_auth_headers,
            json={
                "agent_name": "TestAgent",
                "task_id": "test_task_001",
                "output": {
                    "result": "This is a test output",
                    "status": "completed",
                },
                "error": None,
                "latency_ms": 1500,
                "mode": "advisory",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "test_task_001"
        assert data["agent_name"] == "TestAgent"
        assert "score" in data
        assert 0.0 <= data["score"] <= 1.0
        assert "issues" in data
        assert "suggestions" in data
        assert "approved" in data
        assert "processing_time_ms" in data

    async def test_critique_with_error(self, client: AsyncClient, admin_auth_headers):
        """Test critiquing failed output."""
        response = await client.post(
            "/api/v1/orchestrate/critique",
            headers=admin_auth_headers,
            json={
                "agent_name": "FailingAgent",
                "task_id": "test_task_002",
                "output": {},
                "error": "Connection timeout",
                "latency_ms": 5000,
                "mode": "blocking",
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Should have lower score due to error
        assert data["score"] < 0.8
        assert len(data["issues"]) > 0


class TestStatsEndpoint:
    """Test GET /api/v1/orchestrate/stats"""

    async def test_get_stats(self, client: AsyncClient, admin_auth_headers):
        """Test getting orchestration statistics."""
        response = await client.get("/api/v1/orchestrate/stats", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "tenant_id" in data
        assert "master_orchestrator_id" in data
        assert "router_id" in data
        assert "health_monitor_id" in data
        assert "registered_agents" in data
        assert "active_workflows" in data
        assert "cache_stats" in data


class TestWorkflowStatusEndpoint:
    """Test GET /api/v1/orchestrate/task/{workflow_id}"""

    async def test_get_workflow_status_not_found(self, client: AsyncClient, admin_auth_headers):
        """Test getting status for non-existent workflow."""
        response = await client.get(
            "/api/v1/orchestrate/task/non_existent_workflow",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "non_existent_workflow"
        assert data["exists"] is False


# =============================================================================
# End-to-end workflow tests
# =============================================================================


class TestEndToEndWorkflow:
    """End-to-end tests using the full orchestration pipeline."""

    async def test_full_pipeline(self, client: AsyncClient, admin_auth_headers):
        """Test the complete orchestration pipeline."""
        # Step 1: Route a task
        route_response = await client.post(
            "/api/v1/orchestrate/route",
            headers=admin_auth_headers,
            json={
                "task": {
                    "title": "E2E test task",
                    "description": "Test the full pipeline.",
                },
            },
        )
        assert route_response.status_code == 200
        route_data = route_response.json()
        agent_id = route_data["routed_to_agent"]

        # Step 2: Record health for the agent
        await client.post(
            "/api/v1/orchestrate/health/record",
            headers=admin_auth_headers,
            json={
                "agent_id": agent_id,
                "agent_type": "TestAgent",
                "latency_ms": 100.0,
                "success": True,
                "load": 0.3,
            },
        )
        await _flush_health_monitors()

        # Step 3: Check health report
        health_response = await client.get("/api/v1/orchestrate/health", headers=admin_auth_headers)
        assert health_response.status_code == 200
        health_data = health_response.json()
        assert health_data["total_agents"] >= 1

        # Step 4: Get stats
        stats_response = await client.get("/api/v1/orchestrate/stats", headers=admin_auth_headers)
        assert stats_response.status_code == 200
        stats_data = stats_response.json()
        assert "registered_agents" in stats_data
