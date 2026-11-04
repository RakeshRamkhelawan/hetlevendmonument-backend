import uuid

import pytest
from httpx import AsyncClient


class TestWorkflowCRUDExtended:
    """Tests for GET/PUT/DELETE /api/v1/workflows/{workflow_id}"""

    @pytest.mark.asyncio
    async def test_workflow_lifecycle(
        self, client: AsyncClient, admin_auth_headers: dict[str, str]
    ):
        """Test full lifecycle: Create -> Get -> Update -> Delete"""

        # 1. Create
        unique_id = f"crud_test_{uuid.uuid4().hex[:8]}"
        request_data = {
            "workflow_id": unique_id,
            "name": "LifeCycle Test",
            "description": "Initial version",
            "spec": {"tasks": [{"id": "t1", "type": "action"}]},
            "timeout": 300,
        }

        create_res = await client.post(
            "/api/v1/workflows/", json=request_data, headers=admin_auth_headers
        )
        assert create_res.status_code == 201
        assert create_res.json()["version"] == 1

        # 2. Get
        get_res = await client.get(f"/api/v1/workflows/{unique_id}", headers=admin_auth_headers)
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["workflow_id"] == unique_id
        assert data["version"] == 1
        assert data["spec"]["tasks"][0]["id"] == "t1"
        assert data["status"] == "active"

        # 3. Update (Create v2)
        update_data = request_data.copy()
        update_data["name"] = "LifeCycle Test Updated"
        update_data["spec"]["tasks"].append({"id": "t2", "type": "decision"})

        # PUT needs to send the full creation request structure as per schema
        put_res = await client.put(
            f"/api/v1/workflows/{unique_id}", json=update_data, headers=admin_auth_headers
        )
        assert put_res.status_code == 200
        put_data = put_res.json()
        assert put_data["version"] == 2
        assert put_data["status"] == "updated"

        # 4. Verify v2 is active
        get_res_v2 = await client.get(f"/api/v1/workflows/{unique_id}", headers=admin_auth_headers)
        assert get_res_v2.status_code == 200
        assert get_res_v2.json()["version"] == 2
        assert len(get_res_v2.json()["spec"]["tasks"]) == 2

        # 6. Delete
        del_res = await client.delete(f"/api/v1/workflows/{unique_id}", headers=admin_auth_headers)
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "deleted"

        # 7. Verify Deleted (should be inactive)
        get_res_deleted = await client.get(
            f"/api/v1/workflows/{unique_id}", headers=admin_auth_headers
        )
        assert get_res_deleted.status_code == 200
        assert get_res_deleted.json()["status"] == "inactive"
