"""Fase 3 Simplified Integration Test - Goal Creation Only"""

from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from fastapi import Depends, FastAPI
from httpx import AsyncClient

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


@pytest.fixture
async def auth_headers(admin_token: str):
    """Return Authorization headers with seeded admin JWT token."""
    return {"Authorization": f"Bearer {admin_token}"}


async def test_create_simple_goal(
    integration_client: AsyncClient, auth_headers: dict, integration_app: FastAPI, postgres_session
):
    """Create a simple mission goal."""
    from src.core.api.v1.company.goal_router import get_goal_service
    from src.core.auth.dependencies import get_current_user
    from src.core.company.goal_service import GoalService
    from src.core.container import TenantContext
    from src.core.models.rbac_models import User

    from src.core.api.v1.company.router import get_company_service
    from src.core.company.company_service import CompanyService

    class MockDBManager:
        def __init__(self, session):
            self._session = session

        @asynccontextmanager
        async def get_session(self):
            yield self._session

    async def override_get_company_service(current_user: User = Depends(get_current_user)):
        tenant_context = TenantContext(
            tenant_id=int(getattr(current_user, "tenant_id")),
            tenant_slug=None,
            bypass_filter=False,
        )
        return cast(
            Any,
            CompanyService(
                db_manager=cast(Any, MockDBManager(postgres_session)),
                tenant_context=tenant_context,
            ),
        )

    async def override_get_goal_service(current_user: User = Depends(get_current_user)):
        tenant_context = TenantContext(
            tenant_id=int(getattr(current_user, "tenant_id")),
            tenant_slug=None,
            bypass_filter=False,
        )
        return cast(
            Any,
            GoalService(
                db_manager=cast(Any, MockDBManager(postgres_session)),
                tenant_context=tenant_context,
            ),
        )

    integration_app.dependency_overrides[get_company_service] = override_get_company_service
    integration_app.dependency_overrides[get_goal_service] = override_get_goal_service

    try:
        # First create a company
        company_response = await integration_client.post(
            "/api/v1/companies",
            json={
                "name": "Goal Test Company",
                "company_type": "enterprise",
                "sector": "technology",
            },
            headers=auth_headers,
        )
        assert company_response.status_code == 201
        company_id = company_response.json()["id"]

        # Create mission
        mission_response = await integration_client.post(
            f"/api/v1/goals?company_id={company_id}",
            json={
                "title": "Company Mission",
                "goal_type": "mission",
                "description": "Our core mission",
            },
            headers=auth_headers,
        )
        print(f"DEBUG: mission_response status: {mission_response.status_code}")
        print(f"DEBUG: mission_response body: {mission_response.text[:500]}")
        assert mission_response.status_code == 201

        data = mission_response.json()
        assert data["title"] == "Company Mission"
        assert data["goal_type"] == "mission"
        assert data["progress_pct"] == 0
    finally:
        for dep in [get_company_service, get_goal_service]:
            if dep in integration_app.dependency_overrides:
                del integration_app.dependency_overrides[dep]
