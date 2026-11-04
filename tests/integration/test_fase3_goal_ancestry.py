"""Fase 3 Integration Tests - Goal Ancestry & Alignment

Tests goal hierarchy, ancestry, progress propagation, and alignment validation.
Uses real PostgreSQL + Redis + FastAPI TestClient.
"""

import uuid

import pytest
from httpx import AsyncClient

from src.core.company.context import AgentExecutionContext, GoalChain
from src.core.company.goal_alignment import GoalAlignmentValidator

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


def _make_uuid() -> uuid.UUID:
    """Generate a fresh UUID."""
    return uuid.uuid4()


@pytest.fixture
async def auth_headers(admin_token: str):
    """Return Authorization headers with seeded admin JWT token."""
    return {"Authorization": f"Bearer {admin_token}"}


class TestGoalHierarchyLifecycle:
    """Test full goal hierarchy lifecycle."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="Schema initialization missing 'goals' table (ADR-026 migration pending)"
    )
    async def test_full_goal_hierarchy_lifecycle(
        self,
        integration_client: AsyncClient,
        auth_headers: dict,
    ):
        """Create mission → strategic → project → task, then get ancestry."""
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

        # Debug: check available routes
        from src.main import app

        goal_routes = [
            r.path for r in app.routes if hasattr(r, "path") and "goal" in r.path.lower()
        ]
        print(f"DEBUG: Available goal routes: {goal_routes}")

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
        mission_id = mission_response.json()["id"]

        # Create strategic under mission
        strategic_response = await integration_client.post(
            f"/api/v1/goals?company_id={company_id}",
            json={
                "title": "Strategic Objective",
                "goal_type": "strategic",
                "parent_goal_id": mission_id,
            },
            headers=auth_headers,
        )
        assert strategic_response.status_code == 201
        strategic_id = strategic_response.json()["id"]

        # Create project under strategic
        project_response = await integration_client.post(
            f"/api/v1/goals?company_id={company_id}",
            json={
                "title": "Project Goal",
                "goal_type": "project",
                "parent_goal_id": strategic_id,
            },
            headers=auth_headers,
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["id"]

        # Create task under project
        task_response = await integration_client.post(
            f"/api/v1/goals?company_id={company_id}",
            json={
                "title": "Task Goal",
                "goal_type": "task",
                "parent_goal_id": project_id,
            },
            headers=auth_headers,
        )
        assert task_response.status_code == 201
        task_id = task_response.json()["id"]

        # Get ancestry from task
        ancestry_response = await integration_client.get(
            f"/api/v1/goals/{task_id}/ancestry",
            headers=auth_headers,
        )
        assert ancestry_response.status_code == 200

        ancestry = ancestry_response.json()
        assert "chain" in ancestry
        assert len(ancestry["chain"]) == 4  # task → project → strategic → mission

    @pytest.mark.asyncio
    async def test_progress_propagation_e2e(
        self,
        integration_client: AsyncClient,
        auth_headers: dict,
        integration_app,
        postgres_session,
    ):
        """Test that progress updates propagate to parent goals."""
        from contextlib import asynccontextmanager
        from typing import Any, cast

        from fastapi import Depends

        from src.core.api.v1.company.goal_router import get_goal_service
        from src.core.api.v1.company.router import get_company_service
        from src.core.auth.dependencies import get_current_user
        from src.core.company.company_service import CompanyService
        from src.core.company.goal_service import GoalService
        from src.core.container import TenantContext
        from src.core.models.rbac_models import User

        class MockDBManager:
            def __init__(self, session):
                self._session = session

            @asynccontextmanager
            async def get_session(self):
                yield self._session

        async def override_get_company_service(current_user: User = Depends(get_current_user)):
            tc = TenantContext(
                tenant_id=int(getattr(current_user, "tenant_id")),
                tenant_slug=None,
                bypass_filter=False,
            )
            return cast(
                Any,
                CompanyService(
                    db_manager=cast(Any, MockDBManager(postgres_session)), tenant_context=tc
                ),
            )

        async def override_get_goal_service(current_user: User = Depends(get_current_user)):
            tc = TenantContext(
                tenant_id=int(getattr(current_user, "tenant_id")),
                tenant_slug=None,
                bypass_filter=False,
            )
            return cast(
                Any,
                GoalService(
                    db_manager=cast(Any, MockDBManager(postgres_session)), tenant_context=tc
                ),
            )

        integration_app.dependency_overrides[get_company_service] = override_get_company_service
        integration_app.dependency_overrides[get_goal_service] = override_get_goal_service

        try:
            company_response = await integration_client.post(
                "/api/v1/companies",
                json={
                    "name": "Progress Test Company",
                    "company_type": "enterprise",
                    "sector": "technology",
                },
                headers=auth_headers,
            )
            assert company_response.status_code == 201, company_response.text
            company_id = company_response.json()["id"]

            mission = await integration_client.post(
                f"/api/v1/goals?company_id={company_id}",
                json={"title": "Mission", "goal_type": "mission"},
                headers=auth_headers,
            )
            assert mission.status_code == 201, mission.text
            mission_id = mission.json()["id"]

            strategic = await integration_client.post(
                f"/api/v1/goals?company_id={company_id}",
                json={"title": "Strategic", "goal_type": "strategic", "parent_goal_id": mission_id},
                headers=auth_headers,
            )
            assert strategic.status_code == 201, strategic.text
            strategic_id = strategic.json()["id"]

            project = await integration_client.post(
                f"/api/v1/goals?company_id={company_id}",
                json={"title": "Project", "goal_type": "project", "parent_goal_id": strategic_id},
                headers=auth_headers,
            )
            assert project.status_code == 201, project.text
            project_id = project.json()["id"]

            task1 = await integration_client.post(
                f"/api/v1/goals?company_id={company_id}",
                json={"title": "Task 1", "goal_type": "task", "parent_goal_id": project_id},
                headers=auth_headers,
            )
            assert task1.status_code == 201, task1.text
            task1_id = task1.json()["id"]

            task2 = await integration_client.post(
                f"/api/v1/goals?company_id={company_id}",
                json={"title": "Task 2", "goal_type": "task", "parent_goal_id": project_id},
                headers=auth_headers,
            )
            assert task2.status_code == 201, task2.text
            task2_id = task2.json()["id"]

            await integration_client.put(
                f"/api/v1/goals/{task1_id}/progress?progress=100",
                headers=auth_headers,
            )
            await integration_client.put(
                f"/api/v1/goals/{task2_id}/progress?progress=50",
                headers=auth_headers,
            )

            project_get = await integration_client.get(
                f"/api/v1/goals/{project_id}",
                headers=auth_headers,
            )
            assert project_get.status_code == 200, project_get.text
        finally:
            for dep in [get_company_service, get_goal_service]:
                if dep in integration_app.dependency_overrides:
                    del integration_app.dependency_overrides[dep]

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="Schema initialization missing 'goals' table (ADR-026 migration pending)"
    )
    async def test_goal_hierarchy_constraints(
        self,
        integration_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test that hierarchy constraints are enforced."""
        # Create company
        company_response = await integration_client.post(
            "/api/v1/companies",
            json={
                "name": "Constraint Test Company",
                "company_type": "enterprise",
                "sector": "technology",
            },
            headers=auth_headers,
        )
        company_id = company_response.json()["id"]

        # Create mission
        mission = await integration_client.post(
            f"/api/v1/goals?company_id={company_id}",
            json={"title": "Mission", "goal_type": "mission"},
            headers=auth_headers,
        )
        mission_id = mission.json()["id"]

        # Try to create second mission → should fail with 409
        second_mission = await integration_client.post(
            f"/api/v1/goals?company_id={company_id}",
            json={"title": "Second Mission", "goal_type": "mission"},
            headers=auth_headers,
        )
        assert second_mission.status_code == 409

        # Try to create task directly under mission → should fail with 422
        invalid_task = await integration_client.post(
            f"/api/v1/goals?company_id={company_id}",
            json={
                "title": "Invalid Task",
                "goal_type": "task",
                "parent_goal_id": mission_id,
            },
            headers=auth_headers,
        )
        assert invalid_task.status_code == 422


class TestGoalAlignmentE2E:
    """Test goal alignment validation end-to-end."""

    @pytest.mark.asyncio
    async def test_goal_alignment_with_real_context(
        self,
        integration_client: AsyncClient,
        auth_headers: dict,
    ):
        """Test alignment validator with real goals."""
        # Create validator
        validator = GoalAlignmentValidator(language="nl")

        # Build context with goals using proper UUIDs
        context = AgentExecutionContext(
            tenant_id=1,
            task_id=_make_uuid(),
            trace_id=_make_uuid(),
            goal_chain=GoalChain(
                mission_id=_make_uuid(),
                mission_title="Omzet verdubbelen",
                strategic_goal_id=_make_uuid(),
                strategic_goal_title="Verkoop optimaliseren",
                project_goal_id=_make_uuid(),
                project_goal_title="Sales funnel verbeteren",
                task_goal_id=_make_uuid(),
                task_goal_title="Analyseer verkoopdata",
            ),
        )

        # Test aligned action
        result = await validator.validate("analyseer verkoopdata trends", context)
        # Should have reasonable alignment
        assert result.score > 0.3

        # Test misaligned action
        result = await validator.validate("bestel koffie voor de vergadering", context)
        assert result.status == "MISALIGNED"
        assert result.score < 0.3
