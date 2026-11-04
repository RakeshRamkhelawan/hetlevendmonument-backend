import pytest
from httpx import AsyncClient

# Import all models to ensure they are registered with Base.metadata
import src.core.governance.models
import src.core.workflow.models
from src.core.models import rbac_models


@pytest.mark.asyncio
class TestWorkflowEndpoints:
    async def test_create_workflow_success(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        """Test successful creation of a new workflow."""
        workflow_data = {
            "workflow_id": "test_workflow_1",
            "name": "My Test Workflow",
            "description": "A workflow for testing purposes",
            "spec": {"tasks": [{"name": "task1", "type": "dummy"}]},
            "timeout": 60,
            "metadata": {"key": "value"},
        }
        response = await client.post(
            "/api/v1/workflows/", json=workflow_data, headers=admin_auth_headers
        )
        assert response.status_code == 201
        assert response.json()["workflow_id"] == "test_workflow_1"
        assert response.json()["version"] == 1

    async def test_create_workflow_new_version(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        """Test creating a new version."""
        workflow_data_v1 = {
            "workflow_id": "test_workflow_versioning",
            "name": "Workflow Versioning Test",
            "description": "Initial version",
            "spec": {"tasks": [{"name": "task_v1"}]},
            "timeout": 60,
            "metadata": {},
        }
        await client.post("/api/v1/workflows/", json=workflow_data_v1, headers=admin_auth_headers)

        workflow_data_v2 = {
            "workflow_id": "test_workflow_versioning",
            "name": "Workflow Versioning Test",
            "description": "Second version",
            "spec": {"tasks": [{"name": "task_v2"}]},
            "timeout": 120,
            "metadata": {"updated": True},
        }
        response = await client.post(
            "/api/v1/workflows/", json=workflow_data_v2, headers=admin_auth_headers
        )
        assert response.status_code == 201
        assert response.json()["version"] == 2

    async def test_create_workflow_missing_fields(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        """Test validation."""
        workflow_data = {
            "workflow_id": "invalid_workflow",
            "description": "Missing name and spec",
        }
        response = await client.post(
            "/api/v1/workflows/", json=workflow_data, headers=admin_auth_headers
        )
        assert response.status_code == 422

    # De uitvoer-tests hieronder hebben een workflow MET een stap nodig: sinds 0bf21333 (2026-10-22, ADR-036 OP-13)
    # weigert de route een workflow zonder stappen met 400 ("De workflow heeft geen stappen"), want die liep
    # tot "succeeded" zonder iets te doen. Daarvoor staat een eigen test hieronder.
    async def test_execute_workflow_success(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        """Test execution."""
        workflow_data = {
            "workflow_id": "executable_workflow",
            "name": "Executable",
            "description": "Desc",
            "spec": {"tasks": [{"name": "task1", "type": "dummy"}]},
            "timeout": 300,
            "metadata": {},
        }
        await client.post("/api/v1/workflows/", json=workflow_data, headers=admin_auth_headers)

        execute_data = {"input_data": {"user": "test"}}
        response = await client.post(
            "/api/v1/workflows/executable_workflow/execute",
            json=execute_data,
            headers=admin_auth_headers,
        )
        assert response.status_code == 202
        assert "execution_id" in response.json()

    async def test_execute_workflow_without_steps_is_refused(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        workflow_data = {
            "workflow_id": "workflow_zonder_stappen",
            "name": "Leeg",
            "description": "Desc",
            "spec": {"tasks": []},
            "timeout": 60,
            "metadata": {},
        }
        await client.post("/api/v1/workflows/", json=workflow_data, headers=admin_auth_headers)

        response = await client.post(
            "/api/v1/workflows/workflow_zonder_stappen/execute", json={}, headers=admin_auth_headers
        )

        assert response.status_code == 400
        assert "geen stappen" in response.text

    async def test_execute_workflow_not_found(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        """Test execution 404."""
        response = await client.post(
            "/api/v1/workflows/non_existent/execute", json={}, headers=admin_auth_headers
        )
        assert response.status_code == 404

    async def test_get_execution_status_success(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        """Test status."""
        workflow_data = {
            "workflow_id": "status_workflow",
            "name": "Status",
            "description": "Desc",
            "spec": {"tasks": [{"name": "task1", "type": "dummy"}]},
            "timeout": 60,
            "metadata": {},
        }
        await client.post("/api/v1/workflows/", json=workflow_data, headers=admin_auth_headers)
        res = await client.post(
            "/api/v1/workflows/status_workflow/execute", json={}, headers=admin_auth_headers
        )
        execution_id = res.json()["execution_id"]

        response = await client.get(
            f"/api/v1/workflows/executions/{execution_id}", headers=admin_auth_headers
        )
        assert response.status_code == 200

    async def test_get_execution_status_not_found(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        response = await client.get(
            "/api/v1/workflows/executions/non_existent", headers=admin_auth_headers
        )
        assert response.status_code == 404

    async def test_list_workflows_success(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        workflow_data = {
            "workflow_id": "list_workflow_1",
            "name": "List",
            "description": "Desc",
            "spec": {"tasks": []},
            "timeout": 60,
            "metadata": {},
        }
        await client.post("/api/v1/workflows/", json=workflow_data, headers=admin_auth_headers)

        response = await client.get("/api/v1/workflows/", headers=admin_auth_headers)
        assert response.status_code == 200
        assert len(response.json()) >= 1

    async def test_list_workflows_pagination(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        for i in range(2):
            workflow_data = {
                "workflow_id": f"page_workflow_{i}",
                "name": f"Page {i}",
                "description": "Desc",
                "spec": {"tasks": []},
                "timeout": 60,
                "metadata": {},
            }
            await client.post("/api/v1/workflows/", json=workflow_data, headers=admin_auth_headers)

        response = await client.get("/api/v1/workflows/?limit=1", headers=admin_auth_headers)
        assert response.status_code == 200
        assert len(response.json()) == 1

    async def test_cancel_execution_success(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        workflow_data = {
            "workflow_id": "cancel_workflow",
            "name": "Cancel",
            "description": "Desc",
            "spec": {"tasks": [{"name": "task1", "type": "dummy"}]},
            "timeout": 60,
            "metadata": {},
        }
        await client.post("/api/v1/workflows/", json=workflow_data, headers=admin_auth_headers)
        res = await client.post(
            "/api/v1/workflows/cancel_workflow/execute", json={}, headers=admin_auth_headers
        )
        execution_id = res.json()["execution_id"]

        cancel_res = await client.post(
            f"/api/v1/workflows/executions/{execution_id}/cancel", headers=admin_auth_headers
        )
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "cancelled"

    async def test_cancel_execution_not_found(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        response = await client.post(
            "/api/v1/workflows/executions/non_existent/cancel", headers=admin_auth_headers
        )
        assert response.status_code == 404
