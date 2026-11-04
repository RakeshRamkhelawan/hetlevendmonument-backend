import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, status
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.focus_builder_endpoints import get_focus_builder_service
from src.core.auth.dependencies import get_current_user, get_current_user_id
from src.core.auth.rbac import Permission
from src.core.database.database import get_async_session, get_db


@pytest.fixture
async def db_session(postgres_session: AsyncSession):
    """Use shared PostgreSQL fixture from conftest."""
    yield postgres_session


@pytest.fixture
def client(db_session: AsyncSession, integration_app, admin_token):
    """
    Use the integration_app from conftest with PostgreSQL db_session.
    Overrides focus-builder-specific dependencies.
    """

    async def override_get_db():
        yield db_session

    def override_get_current_user():
        from types import SimpleNamespace

        return SimpleNamespace(
            id=1,
            email="admin@test.com",
            tenant_id=1,
            is_active=True,
            is_superuser=True,
            roles=["admin"],
        )

    integration_app.dependency_overrides[get_db] = override_get_db
    integration_app.dependency_overrides[get_async_session] = override_get_db
    integration_app.dependency_overrides[get_current_user] = override_get_current_user

    headers = {"Authorization": f"Bearer {admin_token}"}
    with TestClient(integration_app, headers=headers) as test_client:
        yield test_client

    # OPRUIMEN (ADR-036 OP-133). `integration_app` is session-scoped en werd hier gewijzigd zonder
    # dat ooit terug te draaien. De `get_db`-override pinde de GEDEELDE app vast op de
    # function-scoped sessie van DIT bestand; zodra die sloot, deed elke latere test zijn queries
    # op een dode sessie. Gemeten gevolg: zes tests in `test_gatekeeper_api.py` kregen 403 met
    # "requires a tenant administrator role", omdat de rolopzoeking niets meer opleverde.
    #
    # De `get_current_user`-override lekte ook, maar die viel niet op: hij komt uit
    # `auth.dependencies` terwijl de gatekeeper-router `auth.runtime_deps` gebruikt -- twee
    # verschillende objecten, dus de override raakte die route niet en de echte opzoeking liep
    # alsnog over de kapotte sessie.
    for _dep in (get_db, get_async_session, get_current_user):
        integration_app.dependency_overrides.pop(_dep, None)


@pytest.fixture
def mock_ap_service(client: TestClient, db_session: AsyncSession):
    """
    Override FocusBuilderService to use a MOCK ActivePiecesClient.
    This prevents external HTTP calls to ActivePieces during tests.
    """
    from src.domains.flows.service import FocusBuilderService

    async def mock_get_service(session: AsyncSession = Depends(get_db)):
        # Create service with the test session
        service = FocusBuilderService(db=session, tenant_id=1)

        # Mock the AP Client
        service.ap_client = MagicMock()
        service.ap_client.create_flow = AsyncMock(
            return_value={"id": "ap_flow_123", "status": "enabled"}
        )
        service.ap_client.update_flow = AsyncMock(
            return_value={"id": "ap_flow_123", "status": "enabled"}
        )
        service.ap_client.delete_flow = AsyncMock(return_value=True)
        service.ap_client.trigger_flow = AsyncMock(
            return_value={"execution_id": "exec_123", "status": "SUCCEEDED"}
        )
        service.ap_client.execute_workflow = AsyncMock(
            return_value={
                "success": True,
                "flow_id": "ap_flow_123",
                "run_id": "run_123",
                "status": "SUCCEEDED",
            }
        )
        service.ap_client.list_pieces = AsyncMock(
            return_value=[
                SimpleNamespace(
                    name="store",
                    display_name="Store",
                    displayName="Store",
                    version="1.0.0",
                    description="Store piece",
                    logo_url=None,
                    logoUrl=None,
                    categories=[],
                    actions={},
                    triggers={},
                )
            ]
        )
        return service

    client.app.dependency_overrides[get_focus_builder_service] = mock_get_service
    yield
    client.app.dependency_overrides.pop(get_focus_builder_service, None)


@pytest.fixture
async def seed_data(db_session: AsyncSession):
    """
    Seed Tenant, Role, and User for RBAC testing in PostgreSQL.

    **Eigen nummers in het 9100-bereik, en dat is geen kosmetiek (ADR-036 OP-133).** Deze fixture
    verwijderde tenant 1, rol 1 en gebruikers 1 en 2 -- precies de gezaaide integratiebeheerder --
    en maakte er een eigen versie voor terug met een ANDER e-mailadres. Er was geen teardown, dus
    alles wat daarna in de suite draaide zag die gewijzigde tabellen.

    Gemeten: zes tests in `test_gatekeeper_api.py` kregen daardoor 403 met "requires a tenant
    administrator role". Reproduceerbaar in vaste volgorde; groen met de eerste 153 bestanden, rood
    zodra dit bestand erbij komt.

    Extra wrang: de drie tests hier zijn alle drie `xfail` wegens een Windows-eventloopconflict. Ze
    kunnen dus niet slagen, en sloopten wel zes tests verderop.
    """
    # Clean up existing data in reverse order to avoid FK constraints
    await db_session.execute(text("DELETE FROM user_roles WHERE user_id IN (9101, 9102)"))
    await db_session.execute(text("DELETE FROM role_permissions WHERE role_id = 9101"))
    await db_session.execute(text("DELETE FROM users WHERE id IN (9101, 9102)"))
    await db_session.execute(text("DELETE FROM roles WHERE id = 9101"))
    await db_session.execute(text("DELETE FROM tenants WHERE id = 9101"))
    await db_session.commit()

    # 1. Create Tenant (ID 1)
    await db_session.execute(
        text(
            """
        INSERT INTO tenants (id, name, slug, is_active, created_at, updated_at, max_users, max_agents, max_storage_gb)
        VALUES (9101, 'FocusBuilder Test Tenant', 'fb-test-tenant', true, NOW(), NOW(), 10, 50, 5)
    """
        )
    )

    # 2. Create Admin Role (ID 1)
    await db_session.execute(
        text(
            """
        INSERT INTO roles (id, name, tenant_id, is_active)
        VALUES (9101, 'admin', 9101, true)
    """
        )
    )

    # 3. Create Role Permissions
    await db_session.execute(
        text(
            """
        INSERT INTO role_permissions (role_id, tenant_id, resource, action)
        VALUES (1, 1, '*', 'admin')
    """
        )
    )
    await db_session.execute(
        text(
            """
        INSERT INTO role_permissions (role_id, tenant_id, resource, action)
        VALUES (1, 1, '*', 'write')
    """
        )
    )
    await db_session.execute(
        text(
            """
        INSERT INTO role_permissions (role_id, tenant_id, resource, action)
        VALUES (9101, 9101, '*', 'read')
    """
        )
    )

    # 4. Create Admin User (ID 1)
    await db_session.execute(
        text(
            """
        INSERT INTO users (id, email, hashed_password, tenant_id, is_active, created_at, updated_at)
        VALUES (9101, 'fb-admin@test.com', 'hash', 9101, true, NOW(), NOW())
    """
        )
    )

    # 5. Assign Role to User
    await db_session.execute(
        text(
            """
        INSERT INTO user_roles (user_id, role_id) VALUES (9101, 9101)
    """
        )
    )

    # 6. Create Normal User (ID 2)
    await db_session.execute(
        text(
            """
        INSERT INTO users (id, email, hashed_password, tenant_id, is_active, created_at, updated_at)
        VALUES (9102, 'fb-user@test.com', 'hash', 9101, true, NOW(), NOW())
    """
        )
    )

    await db_session.commit()
    return {"tenant_id": 9101, "admin_id": 9101, "user_id": 9102}


@pytest.mark.xfail(
    reason="Windows ProactorEventLoop conflict: asyncpg connection bound to different loop in TestClient thread"
)
def test_flow_lifecycle_sync(client: TestClient, mock_ap_service, seed_data):
    """
    Test the full lifecycle using TestClient (Sync) + PostgreSQL.
    Authenticated as Admin (User 1).
    """
    # Mock get_current_user to return a UserResponse
    from src.core.auth import UserResponse

    admin_user = UserResponse(
        id=1,
        email="admin@test.com",
        tenant_id=1,
        is_active=True,
    )
    client.app.dependency_overrides[get_current_user] = lambda: admin_user

    tenant_id = seed_data["tenant_id"]

    # 1. Create Flow (with valid graph containing trigger)
    payload = {
        "name": "Sync Test Flow",
        "tenant_id": tenant_id,
        "react_flow_graph": {
            "nodes": [
                {
                    "id": "1",
                    "type": "trigger",
                    "data": {"label": "Start"},
                    "position": {"x": 0, "y": 0},
                }
            ],
            "edges": [],
        },
    }

    res = client.post("/api/v1/focus-builder/flows", json=payload)
    assert res.status_code in [status.HTTP_201_CREATED, status.HTTP_200_OK], res.text
    data = res.json()
    flow_id = data["id"]
    assert data["name"] == payload["name"]

    # 2. Get Flow
    res = client.get(f"/api/v1/focus-builder/flows/{flow_id}")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["id"] == flow_id

    # 3. List
    res = client.get(f"/api/v1/focus-builder/flows?tenant_id={tenant_id}")
    assert res.status_code == status.HTTP_200_OK
    assert len(res.json()) >= 1

    # 4. Execute (Requires Write)
    res = client.post(f"/api/v1/focus-builder/flows/{flow_id}/execute")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["execution_id"] == "exec_123"

    # 5. Delete
    res = client.delete(f"/api/v1/focus-builder/flows/{flow_id}")
    assert res.status_code == status.HTTP_204_NO_CONTENT

    # Verify Gone
    res = client.get(f"/api/v1/focus-builder/flows/{flow_id}")
    assert res.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.xfail(
    reason="Windows ProactorEventLoop conflict: asyncpg connection bound to different loop in TestClient thread"
)
def test_rbac_denial(client: TestClient, mock_ap_service, seed_data):
    """
    Verify 403 when User (2) has no permissions.
    """
    # Override to User 2 (no roles)
    from src.core.auth import UserResponse

    regular_user = UserResponse(
        id=2,
        email="user@test.com",
        tenant_id=1,
        is_active=True,
    )
    client.app.dependency_overrides[get_current_user] = lambda: regular_user

    tenant_id = seed_data["tenant_id"]

    # Try Create (with valid graph)
    payload = {
        "name": "Illegal Flow",
        "tenant_id": tenant_id,
        "react_flow_graph": {
            "nodes": [
                {
                    "id": "1",
                    "type": "trigger",
                    "data": {"label": "Start"},
                    "position": {"x": 0, "y": 0},
                }
            ],
            "edges": [],
        },
    }
    res = client.post("/api/v1/focus-builder/flows", json=payload)
    assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.xfail(
    reason="Windows ProactorEventLoop conflict: asyncpg connection bound to different loop in TestClient thread"
)
def test_catalog_sync_admin(client: TestClient, mock_ap_service, seed_data):
    """
    Verify Admin can sync catalog.
    User 2 cannot.
    """
    from src.core.auth import UserResponse

    # 1. As Admin (User 1)
    admin_user = UserResponse(
        id=1,
        email="admin@test.com",
        tenant_id=1,
        is_active=True,
    )
    client.app.dependency_overrides[get_current_user] = lambda: admin_user
    res = client.post("/api/v1/focus-builder/pieces/sync")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] in ("sync_started", "success")

    # 2. As User 2 (No Role)
    regular_user = UserResponse(
        id=2,
        email="user@test.com",
        tenant_id=1,
        is_active=True,
    )
    client.app.dependency_overrides[get_current_user] = lambda: regular_user
    res = client.post("/api/v1/focus-builder/pieces/sync")
    assert res.status_code == status.HTTP_403_FORBIDDEN
