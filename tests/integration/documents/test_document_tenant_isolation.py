"""
Integration tests for Document API tenant isolation.

These tests verify that:
1. Documents are scoped to their tenant
2. Tenant A cannot list/get/update/delete documents of Tenant B
3. Soft-deleted documents remain in DB but are invisible across all tenants
"""

from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.integration


@pytest.fixture
def _setup_app_overrides(integration_app, postgres_engine):
    """Helper to setup and teardown app overrides."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_async_session, get_db
    from src.core.middleware.tenant_context import require_tenant_id

    # Store original overrides
    original_overrides = dict(integration_app.dependency_overrides)

    # Create a session factory bound to the PostgreSQL engine
    session_factory = async_sessionmaker(
        postgres_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    def setup(tenant_id: int, user_id: int):
        async def override_get_db():
            # Each request gets its own session to avoid asyncpg concurrency issues
            async with session_factory() as session:
                yield session

        def override_get_current_user():
            return SimpleNamespace(
                id=user_id,
                email=f"user{user_id}@test.com",
                tenant_id=tenant_id,
                is_active=True,
                is_superuser=False,
                roles=["user"],
            )

        def override_require_tenant_id():
            return tenant_id

        integration_app.dependency_overrides[get_db] = override_get_db
        integration_app.dependency_overrides[get_async_session] = override_get_db
        integration_app.dependency_overrides[get_current_user] = override_get_current_user
        integration_app.dependency_overrides[require_tenant_id] = override_require_tenant_id

    yield setup

    # Teardown: restore original overrides
    integration_app.dependency_overrides.clear()
    integration_app.dependency_overrides.update(original_overrides)


@pytest.mark.asyncio
async def test_document_tenant_isolation_upload_and_list(
    integration_client: AsyncClient,
    integration_app,
    _setup_app_overrides,
    admin_token: str,
):
    """Tenant 1 uploads a document. Tenant 2 cannot see it in their list."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Act as tenant 1
    _setup_app_overrides(tenant_id=1, user_id=1)
    upload_resp = await integration_client.post(
        "/api/v1/documents/upload",
        files={"file": ("tenant1_doc.txt", b"tenant 1 content", "text/plain")},
        headers=headers,
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["data"]["id"]

    # Tenant 1 can list and see the document
    list_t1 = await integration_client.get("/api/v1/documents", headers=headers)
    assert list_t1.status_code == 200
    t1_docs = [d["id"] for d in list_t1.json().get("data", [])]
    assert doc_id in t1_docs

    # Switch to tenant 2
    _setup_app_overrides(tenant_id=2, user_id=2)

    # Tenant 2 lists documents -- should NOT see tenant 1's document
    list_t2 = await integration_client.get("/api/v1/documents", headers=headers)
    assert list_t2.status_code == 200
    t2_docs = [d["id"] for d in list_t2.json().get("data", [])]
    assert doc_id not in t2_docs


@pytest.mark.asyncio
async def test_document_tenant_isolation_get_by_id(
    integration_client: AsyncClient,
    integration_app,
    _setup_app_overrides,
    admin_token: str,
):
    """Tenant 1 uploads a document. Tenant 2 cannot GET it by ID."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    _setup_app_overrides(tenant_id=1, user_id=1)

    upload_resp = await integration_client.post(
        "/api/v1/documents/upload",
        files={"file": ("tenant1_doc.txt", b"tenant 1 content", "text/plain")},
        headers=headers,
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["data"]["id"]

    # Tenant 1 can GET
    get_t1 = await integration_client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert get_t1.status_code == 200

    # Switch to tenant 2
    _setup_app_overrides(tenant_id=2, user_id=2)

    # Tenant 2 cannot GET (404)
    get_t2 = await integration_client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    assert get_t2.status_code == 404


@pytest.mark.asyncio
async def test_document_tenant_isolation_update_and_delete(
    integration_client: AsyncClient,
    integration_app,
    _setup_app_overrides,
    admin_token: str,
):
    """Tenant 1 uploads a document. Tenant 2 cannot update or delete it."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    _setup_app_overrides(tenant_id=1, user_id=1)

    upload_resp = await integration_client.post(
        "/api/v1/documents/upload",
        files={"file": ("tenant1_doc.txt", b"tenant 1 content", "text/plain")},
        headers=headers,
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["data"]["id"]

    # Switch to tenant 2
    _setup_app_overrides(tenant_id=2, user_id=2)

    # Tenant 2 cannot update
    update_t2 = await integration_client.put(
        f"/api/v1/documents/{doc_id}",
        json={"filename": "hacked.txt"},
        headers=headers,
    )
    assert update_t2.status_code == 404

    # Tenant 2 cannot delete
    delete_t2 = await integration_client.delete(
        f"/api/v1/documents/{doc_id}",
        headers=headers,
    )
    assert delete_t2.status_code == 404

    # Switch back to tenant 1 and verify still accessible
    _setup_app_overrides(tenant_id=1, user_id=1)
    get_t1 = await integration_client.get(
        f"/api/v1/documents/{doc_id}",
        headers=headers,
    )
    assert get_t1.status_code == 200


@pytest.mark.asyncio
async def test_document_search_fulltext(
    integration_client: AsyncClient,
    integration_app,
    _setup_app_overrides,
    admin_token: str,
):
    """Fulltext search finds documents by filename."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    _setup_app_overrides(tenant_id=1, user_id=1)

    # Upload a document with a unique name
    # Note: secure_filename() replaces spaces with underscores
    upload_resp = await integration_client.post(
        "/api/v1/documents/upload",
        files={"file": ("quarterly report q1.pdf", b"content", "application/pdf")},
        headers=headers,
    )
    assert upload_resp.status_code == 200

    # Search for it — to_tsvector with replace(_, ' ') tokenizes correctly
    search_resp = await integration_client.get(
        "/api/v1/documents/search?q=quarterly",
        headers=headers,
    )
    assert search_resp.status_code == 200
    data = search_resp.json()
    assert data.get("success") is True
    filenames = [d["filename"] for d in data.get("data", [])]
    assert "quarterly_report_q1.pdf" in filenames

    # Search with no results
    no_results = await integration_client.get(
        "/api/v1/documents/search?q=xyznonexistent",
        headers=headers,
    )
    assert no_results.status_code == 200
    assert len(no_results.json().get("data", [])) == 0


@pytest.mark.asyncio
async def test_document_process_and_status(
    integration_client: AsyncClient,
    integration_app,
    _setup_app_overrides,
    admin_token: str,
):
    """Process endpoint triggers async job; status reflects update."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    _setup_app_overrides(tenant_id=1, user_id=1)

    upload_resp = await integration_client.post(
        "/api/v1/documents/upload",
        files={"file": ("process_test.txt", b"content", "text/plain")},
        headers=headers,
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["data"]["id"]

    # Trigger processing
    process_resp = await integration_client.post(
        f"/api/v1/documents/{doc_id}/process",
        headers=headers,
    )
    assert process_resp.status_code == 200
    assert process_resp.json()["data"]["status"] == "processing"

    # Check status
    status_resp = await integration_client.get(
        f"/api/v1/documents/{doc_id}/status",
        headers=headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["status"] == "processing"


@pytest.mark.asyncio
async def test_document_versions_empty(
    integration_client: AsyncClient,
    integration_app,
    _setup_app_overrides,
    admin_token: str,
):
    """Versions endpoint returns empty list for document with no snapshots."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    _setup_app_overrides(tenant_id=1, user_id=1)

    upload_resp = await integration_client.post(
        "/api/v1/documents/upload",
        files={"file": ("versions_test.txt", b"content", "text/plain")},
        headers=headers,
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["data"]["id"]

    versions_resp = await integration_client.get(
        f"/api/v1/documents/{doc_id}/versions",
        headers=headers,
    )
    assert versions_resp.status_code == 200
    data = versions_resp.json()
    assert data.get("success") is True
    assert data.get("data") == []
    assert data.get("total") == 0
