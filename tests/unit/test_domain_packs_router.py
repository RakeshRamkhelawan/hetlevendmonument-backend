"""Unit tests for the Domain Packs router.

Covers:
- Tenant isolation (tenant A cannot read/write tenant B data)
- Auth: unauthenticated requests are rejected
- RBAC: mutation endpoints require tenant_admin role
- Route ordering: /stats is reachable before /{pack_id}
- Pagination on list endpoint
- 404 for missing packs
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.domain_packs import router
from src.core.auth.auth_service import UserResponse


_NOW = datetime.now(timezone.utc)


def _make_user(tenant_id: int = 1, roles: list[str] | None = None) -> UserResponse:
    return UserResponse(
        id=1,
        email="test@test.com",
        tenant_id=tenant_id,
        roles=roles or [],
        is_superuser=False,
    )


def _make_admin_user(tenant_id: int = 1) -> UserResponse:
    return UserResponse(
        id=1,
        email="admin@test.com",
        tenant_id=tenant_id,
        roles=["tenant_admin"],
        is_superuser=False,
    )


def _make_pack(tenant_id: int = 1) -> MagicMock:
    pack = MagicMock()
    pack.id = uuid4()
    pack.tenant_id = tenant_id
    pack.name = "Legal Pack"
    pack.department = "Legal"
    pack.version = 1
    pack.description = "Juridische AI-expertise"
    pack.capabilities = ["contracts", "compliance"]
    pack.input_contracts = {}
    pack.output_contracts = {}
    pack.status = "active"
    pack.created_at = _NOW
    pack.updated_at = _NOW
    return pack


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _override_auth(app: FastAPI, user: UserResponse) -> None:
    from src.core.auth.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user


def _override_db(app: FastAPI) -> AsyncMock:
    from src.core.database.database import get_db

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    return mock_db


# ===========================================================================
# AUTH TESTS
# ===========================================================================


@pytest.mark.unit
def test_list_domain_packs_unauthenticated_returns_401(app, client):
    """Unauthenticated request must be rejected."""
    _override_db(app)
    response = client.get("/api/v1/domain-packs")
    assert response.status_code in (401, 403)


@pytest.mark.unit
def test_create_domain_pack_unauthenticated_returns_401(app, client):
    _override_db(app)
    response = client.post("/api/v1/domain-packs", json={})
    assert response.status_code in (401, 403)


# ===========================================================================
# RBAC TESTS
# ===========================================================================


@pytest.mark.unit
def test_create_domain_pack_regular_user_returns_403(app, client):
    """Regular user (no tenant_admin role) must get 403 on create."""
    _override_auth(app, _make_user())
    _override_db(app)

    with patch(
        "src.core.api.domain_packs.DomainPackRepository",
        autospec=True,
    ):
        response = client.post(
            "/api/v1/domain-packs",
            json={"name": "Test", "department": "Legal", "version": 1, "capabilities": []},
        )
    assert response.status_code == 403


@pytest.mark.unit
def test_archive_domain_pack_regular_user_returns_403(app, client):
    """Regular user must get 403 on archive."""
    _override_auth(app, _make_user())
    _override_db(app)
    pack_id = str(uuid4())

    response = client.post(f"/api/v1/domain-packs/{pack_id}/archive")
    assert response.status_code == 403


@pytest.mark.unit
def test_restore_domain_pack_regular_user_returns_403(app, client):
    """Regular user must get 403 on restore."""
    _override_auth(app, _make_user())
    _override_db(app)
    pack_id = str(uuid4())

    response = client.post(f"/api/v1/domain-packs/{pack_id}/restore")
    assert response.status_code == 403


# ===========================================================================
# HAPPY PATH TESTS
# ===========================================================================


@pytest.mark.unit
def test_list_domain_packs_returns_tenant_packs(app, client):
    """Authenticated user sees packs for their tenant."""
    user = _make_user(tenant_id=42)
    _override_auth(app, user)
    _override_db(app)

    pack = _make_pack(tenant_id=42)

    with (
        patch("src.core.api.domain_packs.DomainPackRepository") as MockRepo,
        patch("src.core.api.domain_packs.EvaluationRepository"),
    ):
        instance = MockRepo.return_value
        instance.list_by_tenant = AsyncMock(return_value=[pack])

        response = client.get("/api/v1/domain-packs")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "Legal Pack"
    assert data[0]["tenant_id"] == 42


@pytest.mark.unit
def test_get_domain_pack_returns_correct_pack(app, client):
    """GET /{pack_id} returns the pack when it exists."""
    user = _make_user(tenant_id=1)
    _override_auth(app, user)
    _override_db(app)

    pack = _make_pack(tenant_id=1)
    pack_id = str(pack.id)

    with (
        patch("src.core.api.domain_packs.DomainPackRepository") as MockRepo,
        patch("src.core.api.domain_packs.EvaluationRepository"),
    ):
        instance = MockRepo.return_value
        instance.get_by_id = AsyncMock(return_value=pack)

        response = client.get(f"/api/v1/domain-packs/{pack_id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Legal Pack"


@pytest.mark.unit
def test_stats_endpoint_reachable_before_pack_id_route(app, client):
    """/stats must not be shadowed by /{pack_id} — route ordering check."""
    user = _make_user(tenant_id=1)
    _override_auth(app, user)
    _override_db(app)

    with (
        patch("src.core.api.domain_packs.EvaluationRepository") as MockEvalRepo,
        patch("src.core.api.domain_packs.DomainPackRepository"),
    ):
        instance = MockEvalRepo.return_value
        instance.get_overall_stats = AsyncMock(
            return_value={"total_packs": 3, "active_packs": 2, "total_procedures": 8}
        )

        response = client.get("/api/v1/domain-packs/stats")

    # Must reach the stats endpoint, NOT try to parse "stats" as a UUID
    assert response.status_code == 200
    body = response.json()
    assert "total_packs" in body


@pytest.mark.unit
def test_list_domain_packs_pagination(app, client):
    """Pagination parameters are respected."""
    user = _make_user(tenant_id=1)
    _override_auth(app, user)
    _override_db(app)

    packs = [_make_pack() for _ in range(5)]

    with (
        patch("src.core.api.domain_packs.DomainPackRepository") as MockRepo,
        patch("src.core.api.domain_packs.EvaluationRepository"),
    ):
        instance = MockRepo.return_value
        instance.list_by_tenant = AsyncMock(return_value=packs)

        response = client.get("/api/v1/domain-packs?limit=2&offset=1")

    assert response.status_code == 200
    assert len(response.json()) == 2


# ===========================================================================
# UNHAPPY PATH TESTS
# ===========================================================================


@pytest.mark.unit
def test_get_domain_pack_not_found_returns_404(app, client):
    """GET /{pack_id} returns 404 when pack does not exist in tenant."""
    user = _make_user(tenant_id=1)
    _override_auth(app, user)
    _override_db(app)

    pack_id = str(uuid4())

    with (
        patch("src.core.api.domain_packs.DomainPackRepository") as MockRepo,
        patch("src.core.api.domain_packs.EvaluationRepository"),
    ):
        instance = MockRepo.return_value
        instance.get_by_id = AsyncMock(return_value=None)

        response = client.get(f"/api/v1/domain-packs/{pack_id}")

    assert response.status_code == 404


@pytest.mark.unit
def test_archive_missing_pack_returns_404(app, client):
    """Archive on non-existent pack returns 404."""
    user = _make_admin_user(tenant_id=1)
    _override_auth(app, user)
    _override_db(app)
    pack_id = str(uuid4())

    with (
        patch("src.core.api.domain_packs.DomainPackRepository") as MockRepo,
        patch("src.core.api.domain_packs.EvaluationRepository"),
    ):
        instance = MockRepo.return_value
        instance.archive = AsyncMock(return_value=None)

        response = client.post(f"/api/v1/domain-packs/{pack_id}/archive")

    assert response.status_code == 404


@pytest.mark.unit
def test_get_domain_pack_invalid_uuid_returns_422(app, client):
    """Invalid UUID in path param returns 422."""
    user = _make_user(tenant_id=1)
    _override_auth(app, user)
    _override_db(app)

    response = client.get("/api/v1/domain-packs/not-a-uuid")
    assert response.status_code == 422


# ===========================================================================
# TENANT ISOLATION (SECURITY) TESTS
# ===========================================================================


@pytest.mark.unit
@pytest.mark.security
def test_list_domain_packs_uses_current_user_tenant_id(app, client):
    """Repository must be called with the JWT tenant_id, never a random value."""
    user = _make_user(tenant_id=99)
    _override_auth(app, user)
    _override_db(app)

    with (
        patch("src.core.api.domain_packs.DomainPackRepository") as MockRepo,
        patch("src.core.api.domain_packs.EvaluationRepository"),
    ):
        instance = MockRepo.return_value
        instance.list_by_tenant = AsyncMock(return_value=[])

        client.get("/api/v1/domain-packs")

        instance.list_by_tenant.assert_called_once_with(99)


@pytest.mark.unit
@pytest.mark.security
def test_get_domain_pack_uses_current_user_tenant_id(app, client):
    """get_by_id must be called with the JWT tenant_id."""
    user = _make_user(tenant_id=77)
    _override_auth(app, user)
    _override_db(app)
    pack_id = uuid4()

    with (
        patch("src.core.api.domain_packs.DomainPackRepository") as MockRepo,
        patch("src.core.api.domain_packs.EvaluationRepository"),
    ):
        instance = MockRepo.return_value
        instance.get_by_id = AsyncMock(return_value=None)

        client.get(f"/api/v1/domain-packs/{pack_id}")

        call_args = instance.get_by_id.call_args
        assert call_args[0][0] == 77


# ===========================================================================
# BEHAVIORAL TEST (user perspective)
# ===========================================================================


@pytest.mark.unit
def test_admin_can_create_and_immediately_list_domain_pack(app, client):
    """
    Scenario: Tenant admin activates a new 'HR Pack'.
    Expected: Pack appears in the pack list after creation.
    """
    user = _make_admin_user(tenant_id=5)
    _override_auth(app, user)
    _override_db(app)

    new_pack = _make_pack(tenant_id=5)
    new_pack.name = "HR Pack"

    with (
        patch("src.core.api.domain_packs.DomainPackRepository") as MockRepo,
        patch("src.core.api.domain_packs.EvaluationRepository"),
    ):
        instance = MockRepo.return_value
        instance.create = AsyncMock(return_value=new_pack)
        instance.list_by_tenant = AsyncMock(return_value=[new_pack])

        create_resp = client.post(
            "/api/v1/domain-packs",
            json={
                "name": "HR Pack",
                "department": "HR",
                "version": 1,
                "capabilities": ["cv_screening", "onboarding"],
            },
        )
        assert create_resp.status_code == 201

        list_resp = client.get("/api/v1/domain-packs")
        assert list_resp.status_code == 200
        names = [p["name"] for p in list_resp.json()]
        assert "HR Pack" in names
