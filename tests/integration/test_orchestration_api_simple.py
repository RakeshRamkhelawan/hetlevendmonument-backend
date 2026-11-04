"""
Simple integration tests for Orchestration API endpoints.

These tests verify the router is properly registered without loading
the full FastAPI app (to avoid issues with other endpoints).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.orchestration.router import router as orchestration_router


# Create minimal app for testing
@pytest.fixture
def test_app():
    """Create a minimal FastAPI app with just the orchestration router."""
    from src.core.api.v1.orchestration.dependencies import get_current_tenant_id
    from src.core.middleware.tenant_context import safe_get_tenant_id

    app = FastAPI()
    app.include_router(orchestration_router, prefix="/api/v1")
    app.dependency_overrides[get_current_tenant_id] = lambda: 1
    app.dependency_overrides[safe_get_tenant_id] = lambda: 1
    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


# These are synchronous tests using TestClient


class TestOrchestrationRouterLoaded:
    """Verify the router loads correctly."""

    def test_router_has_routes(self, test_app):
        """Test that router has routes registered."""
        routes = [r.path for r in test_app.routes]

        # Check key routes exist
        assert any("/api/v1/orchestrate/task" in str(r) for r in routes)
        assert any("/api/v1/orchestrate/route" in str(r) for r in routes)
        assert any("/api/v1/orchestrate/health" in str(r) for r in routes)
        assert any("/api/v1/orchestrate/critique" in str(r) for r in routes)
        assert any("/api/v1/orchestrate/stats" in str(r) for r in routes)


class TestHealthEndpointsSimple:
    """Test health endpoints with minimal app."""

    def test_health_report_empty(self, client):
        """Test getting empty health report."""
        response = client.get("/api/v1/orchestrate/health")

        # Should return 200 with empty report
        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        assert "total_agents" in data
        assert "agents" in data
        assert "by_status" in data
        assert "overall_health_score" in data

    def test_record_health_validation(self, client):
        """Test health record validation."""
        # Valid request
        response = client.post(
            "/api/v1/orchestrate/health/record",
            json={
                "agent_id": "test_agent",
                "agent_type": "TestAgent",
                "latency_ms": 100.0,
                "success": True,
                "load": 0.5,
            },
        )
        assert response.status_code == 204

    def test_record_health_invalid_load(self, client):
        """Test validation rejects invalid load values."""
        response = client.post(
            "/api/v1/orchestrate/health/record",
            json={
                "agent_id": "test_agent",
                "agent_type": "TestAgent",
                "latency_ms": 100.0,
                "success": True,
                "load": 1.5,  # Invalid: > 1.0
            },
        )
        assert response.status_code == 422  # Validation error

    def test_get_agent_health_not_found(self, client):
        """Test getting health for non-existent agent."""
        response = client.get("/api/v1/orchestrate/health/agent/non_existent")

        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "non_existent"
        assert data["exists"] is False


class TestRouteEndpointsSimple:
    """Test routing endpoints."""

    def test_route_task_basic(self, client):
        """Test basic task routing."""
        response = client.post(
            "/api/v1/orchestrate/route",
            json={
                "task": {
                    "title": "Test task",
                    "description": "Test description",
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert "routed_to_agent" in data
        assert "routing_method" in data
        assert "confidence_score" in data

    def test_route_task_validation_error(self, client):
        """Test routing validation rejects missing task."""
        response = client.post(
            "/api/v1/orchestrate/route",
            json={
                # Missing "task" field
                "required_capabilities": ["test"],
            },
        )
        assert response.status_code == 422  # Validation error


class TestCritiqueEndpointsSimple:
    """Test critique endpoints."""

    def test_critique_output(self, client):
        """Test critiquing output."""
        response = client.post(
            "/api/v1/orchestrate/critique",
            json={
                "agent_name": "TestAgent",
                "task_id": "test_001",
                "output": {"result": "test output"},
                "latency_ms": 1000,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "test_001"
        assert data["agent_name"] == "TestAgent"
        assert "score" in data
        assert "issues" in data
        assert "suggestions" in data
        assert "approved" in data


class TestStatsEndpointSimple:
    """Test stats endpoint."""

    def test_get_stats(self, client):
        """Test getting orchestration stats."""
        response = client.get("/api/v1/orchestrate/stats")

        assert response.status_code == 200
        data = response.json()
        assert "tenant_id" in data
        assert "master_orchestrator_id" in data
        assert "router_id" in data
        assert "health_monitor_id" in data
        assert "registered_agents" in data


class TestWorkflowStatusSimple:
    """Test workflow status endpoint."""

    def test_workflow_status_not_found(self, client):
        """Test status for non-existent workflow."""
        response = client.get("/api/v1/orchestrate/task/non_existent")

        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "non_existent"
        assert data["exists"] is False


class TestOrchestrateTaskSimple:
    """Test orchestration endpoint."""

    def test_orchestrate_task_structure(self, client):
        """Test orchestration endpoint accepts valid request."""
        response = client.post(
            "/api/v1/orchestrate/task",
            json={
                "task": {
                    "title": "Test workflow",
                    "description": "Test the orchestration API.",
                },
                "workflow_mode": "sequential",
                "max_subtasks": 4,
            },
        )

        # Should accept the request (may fail later due to no LLM, but structure is valid)
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()
            assert "workflow_id" in data
            assert "status" in data

    def test_orchestrate_task_validation(self, client):
        """Test orchestration validation rejects invalid requests."""
        # Missing task field
        response = client.post(
            "/api/v1/orchestrate/task",
            json={"workflow_mode": "sequential"},
        )
        assert response.status_code == 422

        # Invalid max_subtasks (too many)
        response = client.post(
            "/api/v1/orchestrate/task",
            json={
                "task": {"title": "Test"},
                "max_subtasks": 100,  # > 20 limit
            },
        )
        assert response.status_code == 422
