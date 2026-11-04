"""Security tests for pack selector endpoint.

Covers: tenant isolation, double-execution prevention.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.v1.company.pack_selector_router import (
    PackSelectorRequest,
    router,
)
from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db

TENANT_ID = 1
OTHER_TENANT_ID = 99
USER_ID = 7


def _make_user(tenant_id: int = TENANT_ID) -> MagicMock:
    """Return a mock user with the given tenant_id."""
    user = MagicMock()
    user.id = USER_ID
    user.tenant_id = tenant_id
    user.email = "test@example.com"
    return user


def _make_db_mock(company_tenant_id: int = TENANT_ID) -> AsyncMock:
    """Return an AsyncMock session that returns a company with the given tenant_id."""
    db = AsyncMock()

    company = MagicMock()
    company.tenant_id = company_tenant_id
    db.get.return_value = company

    return db


def _make_app(
    company_tenant_id: int = TENANT_ID,
    user_tenant_id: int = TENANT_ID,
    raise_exceptions: bool = True,
) -> TestClient:
    """Build a minimal FastAPI app with the pack selector router and mocked deps."""
    app = FastAPI()
    app.include_router(router)

    db_mock = _make_db_mock(company_tenant_id=company_tenant_id)
    app.dependency_overrides[get_db] = lambda: db_mock
    app.dependency_overrides[get_current_user] = lambda: _make_user(user_tenant_id)

    return TestClient(app, raise_server_exceptions=raise_exceptions)


class TestPackSelectorTenantIsolation:
    """Users may only access companies within their own tenant."""

    def test_access_own_company_succeeds(self):
        """Request for a company in the user's own tenant is allowed."""
        client = _make_app(company_tenant_id=TENANT_ID, user_tenant_id=TENANT_ID)

        with patch(
            "src.core.api.v1.company.pack_selector_router._execute_pack_selection"
        ) as mock_execute:
            mock_execute.return_value = []
            response = client.post("/pack-selector", json={"company_id": str(uuid4())})

        assert response.status_code == 200
        assert response.json() == []

    def test_access_other_tenant_company_rejected(self):
        """Request for a company in another tenant receives 403."""
        client = _make_app(company_tenant_id=OTHER_TENANT_ID, user_tenant_id=TENANT_ID)

        response = client.post("/pack-selector", json={"company_id": str(uuid4())})

        assert response.status_code == 403
        assert "Access denied" in response.text

    def test_nonexistent_company_rejected(self):
        """Request for a non-existent company receives 403."""
        app = FastAPI()
        app.include_router(router)

        db_mock = AsyncMock()
        db_mock.get.return_value = None  # Company not found
        app.dependency_overrides[get_db] = lambda: db_mock
        app.dependency_overrides[get_current_user] = lambda: _make_user(TENANT_ID)

        client = TestClient(app)
        response = client.post("/pack-selector", json={"company_id": str(uuid4())})

        assert response.status_code == 403
        assert "Access denied" in response.text


class TestPackSelectorNoDoubleExecution:
    """The endpoint must never call _execute_pack_selection twice."""

    def test_single_execution_on_success(self):
        """On success, _execute_pack_selection is called exactly once."""
        client = _make_app(company_tenant_id=TENANT_ID, user_tenant_id=TENANT_ID)

        with patch(
            "src.core.api.v1.company.pack_selector_router._execute_pack_selection"
        ) as mock_execute:
            mock_execute.return_value = []
            response = client.post("/pack-selector", json={"company_id": str(uuid4())})

        assert response.status_code == 200
        assert (
            mock_execute.call_count == 1
        ), f"Expected 1 call to _execute_pack_selection, got {mock_execute.call_count}"

    def test_single_execution_on_failure(self):
        """Even if _execute_pack_selection raises, it is called exactly once."""
        client = _make_app(
            company_tenant_id=TENANT_ID, user_tenant_id=TENANT_ID, raise_exceptions=False
        )

        with patch(
            "src.core.api.v1.company.pack_selector_router._execute_pack_selection"
        ) as mock_execute:
            mock_execute.side_effect = RuntimeError("Simulated failure")
            response = client.post("/pack-selector", json={"company_id": str(uuid4())})

        assert response.status_code == 500
        assert (
            mock_execute.call_count == 1
        ), f"Expected 1 call to _execute_pack_selection, got {mock_execute.call_count}"
