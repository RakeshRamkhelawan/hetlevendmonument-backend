import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.rbac import Permission
from src.core.services.rbac_service import RBACService


@pytest.fixture(autouse=True)
def mock_activepieces_client():
    """Mock ActivePiecesClient entirely to suppress ValueError and provide dummy create_flow."""
    from unittest.mock import AsyncMock, Mock, patch

    mock_client_instance = Mock()
    # Mock methods used in the service interactively
    mock_client_instance.create_flow = AsyncMock(
        return_value={"id": "dummy-flow-id", "version": {"displayName": "mock-flow"}}
    )
    mock_client_instance.update_flow = AsyncMock(return_value={"id": "dummy-flow-id"})
    mock_client_instance.list_project_flows = AsyncMock(return_value=[])
    mock_client_instance.trigger_flow = AsyncMock(
        return_value={"id": "dummy-run-id", "status": "SUCCEEDED"}
    )
    # private method called internally by service
    mock_client_instance._find_project_for_tenant = AsyncMock(return_value="dummy-project-id")

    # "src.domains.flows.service.ActivePiecesClient" is where the service imports it
    with patch(
        "src.domains.flows.service.ActivePiecesClient",
        return_value=mock_client_instance,
    ):
        yield mock_client_instance


@pytest.mark.asyncio
async def test_guest_cannot_create_flow(integration_client: AsyncClient):
    """Test that unauthenticated users cannot create flows."""
    resp = await integration_client.post(
        "/api/v1/focus-builder/flows",
        json={
            "name": "Guest Flow",
            "description": "Attempt by guest",
            "react_flow_graph": {},
        },
    )
    # Should be 401 Unauthorized
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_user_without_permission_cannot_create_flow(
    integration_client: AsyncClient,
    test_user,
    test_token,
    postgres_session: AsyncSession,
):
    """Test that authenticated user WITHOUT permission gets 403."""
    headers = {"Authorization": f"Bearer {test_token}"}

    # Ensure no roles in DB for this user/tenant context
    rbac = RBACService(postgres_session)
    await rbac.revoke_role(test_user["id"], "admin", test_user["tenant_id"])
    await rbac.revoke_role(test_user["id"], "user", test_user["tenant_id"])

    resp = await integration_client.post(
        "/api/v1/focus-builder/flows",
        json={
            "name": "Unauthorized Flow",
            "description": "Attempt by user without perm",
            "react_flow_graph": {"nodes": [], "edges": []},
        },
        headers=headers,
    )

    # Should be 403 Forbidden
    assert resp.status_code == 403
    assert "Missing permission" in resp.text or "User not found" in resp.text


@pytest.mark.asyncio
async def test_user_with_permission_can_create_flow(
    integration_client: AsyncClient,
    test_token,
    test_user,
    postgres_session: AsyncSession,
):
    """Test that authenticated user WITH `workflows:publish` can create flow (wfb-dag1 stap 1)."""
    headers = {"Authorization": f"Bearer {test_token}"}

    # Sinds wfb-dag1 stap 1 vraagt de route require_resource_permission("workflows", "publish");
    # het oude `*:write` volstaat niet meer.

    rbac = RBACService(postgres_session)
    role_name = "workflow_publisher"

    # Create role with broad permissions to satisfy check
    permissions = [{"resource": "workflows", "action": "publish"}]

    # Try creating role, ignore if exists
    existing_roles = await rbac.list_roles(test_user["tenant_id"])
    if not any(r.name == role_name for r in existing_roles):
        await rbac.create_role(
            name=role_name,
            description="Mag workflows publiceren",
            permissions=permissions,
            tenant_id=test_user["tenant_id"],
        )

    # Assign the role (RBACService commits internally to savepoint)
    await rbac.assign_role(test_user["id"], role_name, test_user["tenant_id"])

    # Attempt to create (Minimal valid payload)
    resp = await integration_client.post(
        "/api/v1/focus-builder/flows",
        json={
            "name": "Authorized Flow",
            "description": "Created with permission",
            "react_flow_graph": {"nodes": [], "edges": []},
        },
        headers=headers,
    )

    # 201 Created expected
    if resp.status_code != 201:
        print(f"Failed to create flow: {resp.text}")

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Authorized Flow"
