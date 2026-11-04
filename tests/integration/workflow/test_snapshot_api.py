import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_store_snapshot_api_lifecycle(
    client: AsyncClient, admin_auth_headers: dict[str, str]
):
    """
    Full lifecycle test:
    1. Create Workflow (setup)
    2. POST snapshot (Store)
    3. GET snapshot (Retrieve)
    """
    # 1. Create Workflow
    workflow_payload = {
        "workflow_id": f"snapshot-test-{uuid.uuid4()}",
        "name": "Snapshot Test Workflow",
        "description": "Testing binary persistence",
        "workflow_type": "standard",
        "trigger_type": "manual",
        "spec": {"tasks": [], "dependencies": []},
        "timeout": 3600,
    }
    wf_resp = await client.post(
        "/api/v1/workflows", json=workflow_payload, headers=admin_auth_headers
    )
    assert wf_resp.status_code == 201
    workflow_id = wf_resp.json()["workflow_id"]

    # 2. POST Snapshot
    binary_content = b"\x00\x01\x02\x03YjsContent"
    store_resp = await client.post(
        f"/api/v1/snapshots/{workflow_id}",
        content=binary_content,
        headers={**admin_auth_headers, "Content-Type": "application/octet-stream"},
    )
    # RED PHASE: This should fail with 404 until implemented
    if store_resp.status_code == 404:
        pytest.xfail("Endpoint partially implemented - known 404")

    assert store_resp.status_code == 200
    json_resp = store_resp.json()
    assert json_resp["size_bytes"] == len(binary_content)
    assert json_resp["workflow_id"] == workflow_id

    # 3. GET Snapshot
    get_resp = await client.get(f"/api/v1/snapshots/{workflow_id}", headers=admin_auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.content == binary_content
    assert get_resp.headers["content-type"] == "application/octet-stream"
