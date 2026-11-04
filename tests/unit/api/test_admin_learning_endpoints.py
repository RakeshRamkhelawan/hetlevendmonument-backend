from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.api.dependencies import require_admin_role
from src.core.api.admin_learning_endpoints import (
    _resolve_tenant_id,
    _resolve_user_id,
    apply_learning_retention_policy,
    export_learning_user_data,
    router,
)
from src.core.database.database import Base, get_db
from src.core.learning.gdpr_models import GDPRExportUserRequest, GDPRRetentionRequest
from src.core.learning.gdpr_service import LearningGDPRService
from src.core.learning.models import LearningExperience
from src.core.models.rbac_models import Tenant
from tests.helpers.limiet_request import echte_request


@pytest.fixture
def admin_user() -> SimpleNamespace:
    return SimpleNamespace(id=5, tenant_id=91, roles=["admin"], email="admin@example.com")


@pytest.fixture
def denied_override():
    async def _deny():
        raise HTTPException(status_code=403, detail="Admin access required")

    return _deny


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session() -> AsyncSession:
    raise RuntimeError("db_session fixture must be overridden per test")


def test_status_endpoint_enforces_admin_role(
    app: FastAPI,
    client: TestClient,
    denied_override,
) -> None:
    app.dependency_overrides[require_admin_role] = denied_override

    response = client.get("/admin/learning/status")

    assert response.status_code == 403


def test_resolve_helpers_support_mapping_users() -> None:
    current_user = {"id": 12, "tenant_id": 91}

    assert _resolve_tenant_id(current_user) == 91
    assert _resolve_user_id(current_user) == 12


@pytest.mark.asyncio
async def test_status_endpoint_returns_learning_counts(
    app: FastAPI, admin_user: SimpleNamespace
) -> None:
    """
    Test that the learning status endpoint returns correct counts.

    This test mocks the LearningGDPRService to avoid database and event loop
    conflicts that can occur when mixing TestClient with async database sessions.
    """
    # Create mock service and response
    mock_service = MagicMock()
    mock_report = MagicMock()
    mock_report.model_dump.return_value = {
        "tenant_id": 91,
        "counts": {"observations": 1, "patterns": 0, "rules": 0},
        "last_updated": "2026-03-18T08:00:00Z",
    }
    mock_service.get_status = AsyncMock(return_value=mock_report)

    # Mock get_db to return a mock session
    mock_session = MagicMock(spec=AsyncSession)

    async def _get_db_override():
        yield mock_session

    # Set up dependency overrides
    app.dependency_overrides[require_admin_role] = lambda: admin_user
    app.dependency_overrides[get_db] = _get_db_override

    # Patch the service class to use our mock
    with patch(
        "src.core.api.admin_learning_endpoints.LearningGDPRService",
        return_value=mock_service,
    ):
        # Use AsyncClient with ASGITransport for proper async testing
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            response = await test_client.get("/admin/learning/status")

    # Verify response
    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == 91
    assert payload["counts"]["observations"] == 1

    # Verify the service was called correctly
    mock_service.get_status.assert_awaited_once_with(tenant_id=91)


@pytest.mark.asyncio
async def test_delete_user_endpoint_requires_admin(app: FastAPI, denied_override) -> None:
    app.dependency_overrides[require_admin_role] = denied_override

    # Use AsyncClient with ASGITransport for proper async testing
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.post(
            "/admin/learning/gdpr/delete-user", json={"user_id": "user-1"}
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_audit_log_endpoint_returns_learning_entries(
    app: FastAPI,
    admin_user: SimpleNamespace,
) -> None:
    from datetime import datetime, timezone

    from src.core.learning.gdpr_models import LearningAuditEntry

    mock_entry = LearningAuditEntry(
        id=1,
        action="learning.observation_created",
        resource="observation:1",
        user_id=None,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        details={},
    )
    mock_service = MagicMock()
    mock_service.get_audit_log = AsyncMock(return_value=[mock_entry])

    async def _fake_db():
        yield MagicMock()

    app.dependency_overrides[require_admin_role] = lambda: admin_user
    app.dependency_overrides[get_db] = _fake_db

    with patch(
        "src.core.api.admin_learning_endpoints.LearningGDPRService",
        return_value=mock_service,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            response = await test_client.get("/admin/learning/audit-log")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["action"] == "learning.observation_created"
    mock_service.get_audit_log.assert_awaited_once_with(tenant_id=91, limit=50, offset=0)


@pytest.mark.asyncio
async def test_export_endpoint_returns_serialized_payload(
    admin_user: SimpleNamespace,
) -> None:
    async def _export_user_data(
        self, user_id: str, tenant_id: int, requested_by_user_id: int | None
    ):
        class ExportResult:
            def model_dump(self):
                return {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "requested_by": requested_by_user_id,
                }

        return ExportResult()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(LearningGDPRService, "export_user_data", _export_user_data)
        payload = await export_learning_user_data(
            http_request=echte_request(),
            request=GDPRExportUserRequest(user_id="user-1"),
            current_user=admin_user,
            db=None,
        )

    assert payload["user_id"] == "user-1"
    assert payload["tenant_id"] == 91
    assert payload["requested_by"] == 5


@pytest.mark.asyncio
async def test_retention_endpoint_uses_jwt_tenant_not_request_body(
    admin_user: SimpleNamespace,
) -> None:
    """tenant_id in the request body must be ignored -- JWT context is authoritative (ADR-003).

    Sprint 2A security fix: removed request.tenant_id fallback to prevent
    privilege escalation where an admin could act on another tenant's data.
    The endpoint always uses _resolve_tenant_id(current_user) == admin_user.tenant_id == 91.
    """

    async def _apply_retention_policy(
        self,
        max_age_days: int,
        tenant_id: int,
        requested_by_user_id: int | None,
    ):
        class RetentionResult:
            def model_dump(self):
                return {
                    "max_age_days": max_age_days,
                    "tenant_id": tenant_id,
                    "requested_by": requested_by_user_id,
                }

        return RetentionResult()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(LearningGDPRService, "apply_retention_policy", _apply_retention_policy)
        payload = await apply_learning_retention_policy(
            # tenant_id=99 in body must be ignored -- JWT context (91) wins
            http_request=echte_request(),
            request=GDPRRetentionRequest(max_age_days=30, tenant_id=99),
            current_user=admin_user,
            db=None,
        )

    # Must equal admin_user.tenant_id (91), NOT the body value (99)
    assert payload["tenant_id"] == 91
    assert payload["requested_by"] == 5


# =============================================================================
# ADR-026 Tenant LLM Budget Admin Endpoint Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_llm_budget_returns_defaults_when_no_record(
    app: FastAPI,
    admin_user: SimpleNamespace,
) -> None:
    """Test GET /admin/learning/tenants/{id}/llm-budget returns defaults."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(Tenant(id=91, name="Admin Tenant", slug="admin-tenant", is_active=True))
        await session.commit()

    async def _get_db_override():
        async with AsyncSession(engine, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[require_admin_role] = lambda: admin_user
    app.dependency_overrides[get_db] = _get_db_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.get("/admin/learning/tenants/91/llm-budget")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == 91
    assert payload["budget_eur_soft"] == 10.0
    assert payload["budget_eur_hard"] == 50.0
    assert payload["spent_eur"] == 0.0

    await engine.dispose()


@pytest.mark.asyncio
async def test_put_llm_budget_creates_record(
    app: FastAPI,
    admin_user: SimpleNamespace,
) -> None:
    """Test PUT /admin/learning/tenants/{id}/llm-budget creates budget record."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(Tenant(id=91, name="Admin Tenant", slug="admin-tenant", is_active=True))
        await session.commit()

    async def _get_db_override():
        async with AsyncSession(engine, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[require_admin_role] = lambda: admin_user
    app.dependency_overrides[get_db] = _get_db_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.put(
            "/admin/learning/tenants/91/llm-budget",
            json={"budget_eur_soft": 25.0, "budget_eur_hard": 100.0},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tenant_id"] == 91
    assert payload["budget_eur_soft"] == 25.0
    assert payload["budget_eur_hard"] == 100.0

    # Verify GET returns the updated values
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.get("/admin/learning/tenants/91/llm-budget")

    assert response.status_code == 200
    payload = response.json()
    assert payload["budget_eur_soft"] == 25.0
    assert payload["budget_eur_hard"] == 100.0

    await engine.dispose()


@pytest.mark.asyncio
async def test_put_llm_budget_rejects_hard_less_than_soft(
    app: FastAPI,
    admin_user: SimpleNamespace,
) -> None:
    """Test PUT rejects hard cap less than soft cap."""
    mock_session = MagicMock(spec=AsyncSession)

    async def _get_db_override():
        yield mock_session

    app.dependency_overrides[require_admin_role] = lambda: admin_user
    app.dependency_overrides[get_db] = _get_db_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        response = await test_client.put(
            "/admin/learning/tenants/91/llm-budget",
            json={"budget_eur_soft": 50.0, "budget_eur_hard": 30.0},
        )

    assert response.status_code == 422
