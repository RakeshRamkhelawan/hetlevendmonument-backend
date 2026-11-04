"""
Workflow Versioning Endpoints Integration Tests
================================================

Tests for REST endpoints for workflow version management.

Test Classes:
- TestSaveVersionEndpoint: POST /{workflow_id}/versions
- TestGetVersionHistoryEndpoint: GET /{workflow_id}/versions
- TestGetSpecificVersionEndpoint: GET /{workflow_id}/versions/{version_number}
- TestRollbackEndpoint: POST /{workflow_id}/versions/{version_number}/rollback
- TestCompareVersionsEndpoint: GET /{workflow_id}/compare
"""

from typing import Any, Dict

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.workflow_refinement_endpoints import (
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
)
from src.core.models.rbac_models import Role, Tenant, User


@pytest.fixture
def test_user_with_token(normal_user_with_workflow_scopes: Dict[str, Any]) -> Dict[str, Any]:
    """Use a token fixture that includes workflow scopes required by versioning endpoints."""
    return normal_user_with_workflow_scopes


@pytest.mark.asyncio
@pytest.mark.integration
class TestSaveVersionEndpoint:
    """Tests for saving workflow versions via REST."""

    async def test_save_version_creates_new_snapshot(
        self,
        async_client: AsyncClient,
        test_user_with_token: Dict[str, Any],
        async_session: AsyncSession,
    ):
        """Verify version save endpoint creates snapshot."""
        token = test_user_with_token["token"]

        payload = {
            "workflow_id": "wf_api_1",
            "name": "Test Workflow",
            "workflow": {
                "nodes": [
                    {
                        "id": "n1",
                        "name": "Start",
                        "type": "start",
                        "x": 0,
                        "y": 0,
                        "data": {},
                    }
                ],
                "edges": [],
            },
            "change_description": "Initial snapshot",
            "tags": ["initial"],
        }

        response = await async_client.post(
            "/api/v1/workflows/wf_api_1/versions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["version_number"] == 1
        assert data["name"] == "Test Workflow"
        assert data["change_description"] == "Initial snapshot"
        assert "initial" in data["tags"]

    async def test_save_version_requires_auth(self, async_client: AsyncClient):
        """Verify endpoint requires authentication."""
        payload = {
            "workflow_id": "wf_test",
            "name": "Test",
            "workflow": {"nodes": [], "edges": []},
        }

        response = await async_client.post(
            "/api/v1/workflows/wf_test/versions",
            json=payload,
        )

        assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.integration
class TestGetVersionHistoryEndpoint:
    """Tests for retrieving version history via REST."""

    async def test_get_version_history_returns_versions(
        self, async_client: AsyncClient, test_user_with_token
    ):
        """Verify history endpoint returns versions ordered by recency."""
        token = test_user_with_token["token"]

        # Create multiple versions first
        for i in range(1, 4):
            payload = {
                "workflow_id": "wf_hist",
                "name": f"Version {i}",
                "workflow": {"nodes": [], "edges": []},
                "change_description": f"Change {i}",
            }
            response = await async_client.post(
                "/api/v1/workflows/wf_hist/versions",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )

        # Get history
        response = await async_client.get(
            "/api/v1/workflows/wf_hist/versions",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "versions" in data
        assert len(data["versions"]) == 3
        # Newest first
        assert data["versions"][0]["version_number"] == 3
        assert data["versions"][1]["version_number"] == 2
        assert data["versions"][2]["version_number"] == 1

    async def test_get_version_history_with_limit(
        self, async_client: AsyncClient, test_user_with_token
    ):
        """Verify limit parameter restricts results."""
        token = test_user_with_token["token"]

        # Create versions (3 is enough to prove limit=2 restricts results;
        # 5 iterations exceeded the savepoint-managed connection commit budget
        # on Windows/IocpProactor, causing ConnectionDoesNotExistError)
        for i in range(1, 4):
            payload = {
                "workflow_id": "wf_lim",
                "name": f"v{i}",
                "workflow": {"nodes": [], "edges": []},
            }
            response = await async_client.post(
                "/api/v1/workflows/wf_lim/versions",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )

        # Get with limit
        response = await async_client.get(
            "/api/v1/workflows/wf_lim/versions?limit=2",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["versions"]) == 2


@pytest.mark.asyncio
@pytest.mark.integration
class TestGetSpecificVersionEndpoint:
    """Tests for retrieving specific versions."""

    async def test_get_specific_version_returns_full_definition(
        self, async_client: AsyncClient, test_user_with_token
    ):
        """Verify endpoint returns complete version definition."""
        token = test_user_with_token["token"]

        # Create a version with specific content
        payload = {
            "workflow_id": "wf_spec",
            "name": "Specific",
            "workflow": {
                "nodes": [
                    {
                        "id": "n1",
                        "name": "Node 1",
                        "type": "start",
                        "x": 0,
                        "y": 0,
                        "data": {},
                    },
                    {
                        "id": "n2",
                        "name": "Node 2",
                        "type": "end",
                        "x": 100,
                        "y": 0,
                        "data": {},
                    },
                ],
                "edges": [{"id": "e1", "source": "n1", "target": "n2", "type": "smoothstep"}],
            },
            "change_description": "Test version",
        }

        create_response = await async_client.post(
            "/api/v1/workflows/wf_spec/versions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_response.status_code == 201

        # Get specific version
        response = await async_client.get(
            "/api/v1/workflows/wf_spec/versions/1",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version_number"] == 1
        assert data["name"] == "Specific"
        assert "workflow_spec" in data
        assert len(data["workflow_spec"]["nodes"]) == 2
        assert len(data["workflow_spec"]["edges"]) == 1

    async def test_get_specific_version_not_found(
        self, async_client: AsyncClient, test_user_with_token
    ):
        """Verify 404 for non-existent version."""
        token = test_user_with_token["token"]

        response = await async_client.get(
            "/api/v1/workflows/wf_none/versions/999",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
class TestRollbackEndpoint:
    """Tests for rollback functionality."""

    async def test_rollback_creates_new_version_with_old_content(
        self, async_client: AsyncClient, test_user_with_token
    ):
        """Verify rollback endpoint creates version with target version content."""
        token = test_user_with_token["token"]

        # Create v1 with 1 node
        payload_v1 = {
            "workflow_id": "wf_rb",
            "name": "Initial",
            "workflow": {
                "nodes": [
                    {
                        "id": "n1",
                        "name": "Node",
                        "type": "start",
                        "x": 0,
                        "y": 0,
                        "data": {},
                    }
                ],
                "edges": [],
            },
        }
        response = await async_client.post(
            "/api/v1/workflows/wf_rb/versions",
            json=payload_v1,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Create v2 with 2 nodes
        payload_v2 = {
            "workflow_id": "wf_rb",
            "name": "Updated",
            "workflow": {
                "nodes": [
                    {
                        "id": "n1",
                        "name": "Node 1",
                        "type": "start",
                        "x": 0,
                        "y": 0,
                        "data": {},
                    },
                    {
                        "id": "n2",
                        "name": "Node 2",
                        "type": "end",
                        "x": 100,
                        "y": 0,
                        "data": {},
                    },
                ],
                "edges": [],
            },
        }
        response = await async_client.post(
            "/api/v1/workflows/wf_rb/versions",
            json=payload_v2,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Rollback to v1
        response = await async_client.post(
            "/api/v1/workflows/wf_rb/versions/1/rollback",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["new_version_number"] == 3
        # Verify content is from v1 (1 node)
        assert len(data["workflow"]["nodes"]) == 1

    async def test_rollback_adds_rollback_tag(
        self, async_client: AsyncClient, test_user_with_token
    ):
        """Verify rollback version has 'rollback' tag."""
        token = test_user_with_token["token"]

        # Create initial version
        payload = {
            "workflow_id": "wf_tag",
            "name": "V1",
            "workflow": {"nodes": [], "edges": []},
            "tags": ["initial"],
        }
        response = await async_client.post(
            "/api/v1/workflows/wf_tag/versions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Create second version
        payload["name"] = "V2"
        response = await async_client.post(
            "/api/v1/workflows/wf_tag/versions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Rollback
        response = await async_client.post(
            "/api/v1/workflows/wf_tag/versions/1/rollback",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Get the rollback version
        get_response = await async_client.get(
            f"/api/v1/workflows/wf_tag/versions/{data['new_version_number']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        version_data = get_response.json()
        assert "rollback" in version_data["tags"]


@pytest.mark.asyncio
@pytest.mark.integration
class TestCompareVersionsEndpoint:
    """Tests for version comparison."""

    async def test_compare_versions_shows_changes(
        self, async_client: AsyncClient, test_user_with_token
    ):
        """Verify comparison endpoint shows node/edge changes."""
        token = test_user_with_token["token"]

        # Create v1: 2 nodes
        payload_v1 = {
            "workflow_id": "wf_cmp",
            "name": "V1",
            "workflow": {
                "nodes": [
                    {
                        "id": "n1",
                        "name": "N1",
                        "type": "start",
                        "x": 0,
                        "y": 0,
                        "data": {},
                    },
                    {
                        "id": "n2",
                        "name": "N2",
                        "type": "end",
                        "x": 100,
                        "y": 0,
                        "data": {},
                    },
                ],
                "edges": [],
            },
        }
        response = await async_client.post(
            "/api/v1/workflows/wf_cmp/versions",
            json=payload_v1,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Create v2: 3 nodes
        payload_v2 = {
            "workflow_id": "wf_cmp",
            "name": "V2",
            "workflow": {
                "nodes": [
                    {
                        "id": "n1",
                        "name": "N1",
                        "type": "start",
                        "x": 0,
                        "y": 0,
                        "data": {},
                    },
                    {
                        "id": "n2",
                        "name": "N2",
                        "type": "process",
                        "x": 100,
                        "y": 0,
                        "data": {},
                    },
                    {
                        "id": "n3",
                        "name": "N3",
                        "type": "end",
                        "x": 200,
                        "y": 0,
                        "data": {},
                    },
                ],
                "edges": [],
            },
        }
        response = await async_client.post(
            "/api/v1/workflows/wf_cmp/versions",
            json=payload_v2,
            headers={"Authorization": f"Bearer {token}"},
        )

        # Compare
        response = await async_client.get(
            "/api/v1/workflows/wf_cmp/compare?v1=1&v2=2",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version1"] == 1
        assert data["version2"] == 2
        assert data["nodes_change"] == 1  # 3 - 2 = 1
        assert data["edges_change"] == 0

    async def test_compare_versions_invalid_versions(
        self, async_client: AsyncClient, test_user_with_token
    ):
        """Verify 400 for invalid version comparison."""
        token = test_user_with_token["token"]

        response = await async_client.get(
            "/api/v1/workflows/wf_none/compare?v1=1&v2=2",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
