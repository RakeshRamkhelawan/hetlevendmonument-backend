"""
Unit tests for Demo Playground Endpoints (TASK-001)
Target: 85%+ coverage for demo_endpoints.py
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Import the demo endpoints router
from src.core.api.demo_endpoints import (
    DEMO_WORKFLOWS,
    DemoWorkflow,
    execute_demo_workflow,
    get_demo_workflows,
    router,
)


class TestDemoWorkflowModel:
    """Test DemoWorkflow Pydantic model"""

    def test_demo_workflow_creation(self):
        """Test creating a DemoWorkflow instance"""
        wf = DemoWorkflow(
            id="test-1",
            name="Test Workflow",
            description="A test workflow",
            category="test",
        )
        assert wf.id == "test-1"
        assert wf.name == "Test Workflow"
        assert wf.description == "A test workflow"
        assert wf.category == "test"

    def test_demo_workflow_serialization(self):
        """Test DemoWorkflow JSON serialization"""
        wf = DemoWorkflow(
            id="test-2",
            name="Another Test",
            description="Description",
            category="analytics",
        )
        data = wf.model_dump()
        assert data["id"] == "test-2"
        assert "name" in data
        assert "description" in data
        assert "category" in data


class TestDemoWorkflowsData:
    """Test pre-defined demo workflows"""

    def test_demo_workflows_exist(self):
        """Test that demo workflows are defined"""
        assert len(DEMO_WORKFLOWS) == 3

    def test_demo_workflows_ids(self):
        """Test demo workflow IDs"""
        ids = [wf.id for wf in DEMO_WORKFLOWS]
        assert "demo-1" in ids
        assert "demo-2" in ids
        assert "demo-3" in ids

    def test_demo_workflows_categories(self):
        """Test demo workflow categories"""
        categories = [wf.category for wf in DEMO_WORKFLOWS]
        assert "analytics" in categories
        assert "content" in categories
        assert "translation" in categories

    def test_demo_workflows_have_descriptions(self):
        """Test all workflows have descriptions"""
        for wf in DEMO_WORKFLOWS:
            assert wf.description
            assert len(wf.description) > 10


class TestGetDemoWorkflowsEndpoint:
    """Test GET /api/v1/demo/workflows endpoint"""

    @pytest.mark.asyncio
    async def test_get_demo_workflows_returns_list(self):
        """Test endpoint returns list of workflows"""
        result = await get_demo_workflows()
        assert isinstance(result, list)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_get_demo_workflows_structure(self):
        """Test each workflow has required fields"""
        result = await get_demo_workflows()
        for wf in result:
            assert hasattr(wf, "id")
            assert hasattr(wf, "name")
            assert hasattr(wf, "description")
            assert hasattr(wf, "category")


class TestExecuteDemoWorkflowEndpoint:
    """Test POST /api/v1/demo/execute/{workflow_id} endpoint"""

    @pytest.mark.asyncio
    async def test_execute_valid_workflow_demo1(self):
        """Test executing demo-1 workflow"""
        result = await execute_demo_workflow("demo-1")
        assert result["status"] == "completed"
        assert result["workflow_id"] == "demo-1"
        assert "churn_risk_score" in result["result"]
        assert "at_risk_donors" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_valid_workflow_demo2(self):
        """Test executing demo-2 workflow"""
        result = await execute_demo_workflow("demo-2")
        assert result["status"] == "completed"
        assert result["workflow_id"] == "demo-2"
        assert "generated_content" in result["result"]
        assert "word_count" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_valid_workflow_demo3(self):
        """Test executing demo-3 workflow"""
        result = await execute_demo_workflow("demo-3")
        assert result["status"] == "completed"
        assert result["workflow_id"] == "demo-3"
        assert "original" in result["result"]
        assert "translated" in result["result"]
        assert "confidence" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_invalid_workflow_raises_404(self):
        """Test executing invalid workflow returns 404"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await execute_demo_workflow("invalid-id")
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_execute_returns_workflow_name(self):
        """Test execution result includes workflow name"""
        result = await execute_demo_workflow("demo-1")
        assert "workflow_name" in result
        assert result["workflow_name"] == "Donor Churn Analysis"

    @pytest.mark.asyncio
    async def test_execute_returns_message(self):
        """Test execution result includes success message"""
        result = await execute_demo_workflow("demo-2")
        assert "message" in result
        assert "successfully" in result["message"].lower()


class TestDemoEndpointsRouterIntegration:
    """Integration tests for demo router with FastAPI"""

    def test_router_prefix(self):
        """Test router has correct prefix"""
        assert router.prefix == "/api/v1/demo"

    def test_router_tags(self):
        """Test router has correct tags"""
        assert "demo" in router.tags

    def test_get_workflows_route_exists(self):
        """Test GET /workflows route is registered"""
        routes = [route.path for route in router.routes]
        assert any("/workflows" in route for route in routes)

    def test_execute_route_exists(self):
        """Test POST /execute route is registered"""
        routes = [route.path for route in router.routes]
        assert any("/execute" in route for route in routes)


# FastAPI TestClient integration tests
class TestDemoEndpointsWithTestClient:
    """End-to-end tests with FastAPI TestClient"""

    @pytest.fixture
    def client(self):
        """Create test client with demo router"""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_get_workflows_endpoint_status(self, client):
        """Test GET /api/v1/demo/workflows returns 200"""
        response = client.get("/api/v1/demo/workflows")
        assert response.status_code == 200

    def test_get_workflows_endpoint_json(self, client):
        """Test GET /api/v1/demo/workflows returns valid JSON"""
        response = client.get("/api/v1/demo/workflows")
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3

    def test_execute_workflow_endpoint_success(self, client):
        """Test POST /api/v1/demo/execute/demo-1 returns 200"""
        response = client.post("/api/v1/demo/execute/demo-1")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    def test_execute_workflow_endpoint_not_found(self, client):
        """Test POST with invalid ID returns 404"""
        response = client.post("/api/v1/demo/execute/invalid")
        assert response.status_code == 404

    def test_workflows_response_structure(self, client):
        """Test workflow response has all fields"""
        response = client.get("/api/v1/demo/workflows")
        workflows = response.json()
        for wf in workflows:
            assert "id" in wf
            assert "name" in wf
            assert "description" in wf
            assert "category" in wf


# Edge case tests
class TestDemoEndpointsEdgeCases:
    """Edge case and boundary tests"""

    @pytest.mark.asyncio
    async def test_empty_workflow_id(self):
        """Test empty workflow ID handling"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            await execute_demo_workflow("")

    @pytest.mark.asyncio
    async def test_special_characters_in_id(self):
        """Test special characters in workflow ID"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            await execute_demo_workflow("demo-1'; DROP TABLE workflows;--")

    @pytest.mark.asyncio
    async def test_numeric_workflow_id(self):
        """Test numeric workflow ID"""
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            await execute_demo_workflow("123")
