"""Fase 3 Direct Integration Test - Test GoalService directly"""

import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


@pytest.mark.asyncio
async def test_goal_service_direct(postgres_session: AsyncSession):
    """Test GoalService directly with database session."""
    from src.core.company.goal_service import GoalService
    from src.core.company.schemas import GoalCreate
    from src.core.container import TenantContext

    # Create mock db_manager that uses the test session
    class MockDBManager:
        def __init__(self, session):
            self._session = session

        @asynccontextmanager
        async def get_session(self):
            yield self._session

    tenant_context = TenantContext(
        tenant_id=1,
        tenant_slug="test",
        bypass_filter=False,
    )

    service = GoalService(
        db_manager=MockDBManager(postgres_session),
        tenant_context=tenant_context,
    )

    # First create a company directly in DB
    from sqlalchemy import text

    company_id = uuid.uuid4()
    await postgres_session.execute(
        text(
            """
        INSERT INTO companies (id, tenant_id, name, company_type, sector, status, config)
        VALUES (:id, :tenant_id, :name, :company_type, :sector, :status, :config)
        """
        ),
        {
            "id": str(company_id),
            "tenant_id": 1,
            "name": "Test Company",
            "company_type": "enterprise",
            "sector": "technology",
            "status": "active",
            "config": "{}",
        },
    )
    await postgres_session.commit()

    # Create a mission goal
    goal_data = GoalCreate(
        title="Company Mission",
        goal_type="mission",
        description="Our core mission",
    )

    result = await service.create_goal(company_id, goal_data)

    assert result.title == "Company Mission"
    assert result.goal_type == "mission"
    assert result.progress_pct == 0
    assert result.company_id == company_id
