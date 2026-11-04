"""
Database integration tests for template enrichment.

Tests verify direct database operations using real asyncpg sessions.
No HTTP layer - direct service method calls with real database.
"""

import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.models import Agent
from src.core.company.models import Company, CompanyTemplate, Department
from src.core.company.schemas import TemplateInstantiateRequest
from src.core.company.template_service import TemplateService


class MockTenantContext:
    """Simple mock tenant context for testing."""

    def __init__(self, tenant_id: int = 1):
        self.tenant_id = tenant_id


class MockDBManager:
    """Simple mock for DatabaseManager that yields the session."""

    def __init__(self, session: AsyncSession):
        self._session = session

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield the session for async context manager usage."""
        yield self._session


@pytest.mark.integration
@pytest.mark.asyncio
class TestTemplateEnrichmentDatabaseIntegration:
    """Real database tests for template enrichment logic."""

    async def test_sector_departments_persisted_to_database(self, db_session: AsyncSession) -> None:
        """
        Direct DB test: Verify sector departments are persisted correctly.

        Given: Technologie MKB template in database
        When: TemplateService.instantiate() called
        Then: All 5 departments persisted with correct data
        """
        # Arrange: Create template in DB
        template = CompanyTemplate(
            id=uuid.uuid4(),
            name="Technologie MKB Test",
            company_type="mkb",
            sector="Technologie",
            template_definition={"departments": [{"name": "Management"}]},
            is_platform_template=True,
            status="active",
        )
        db_session.add(template)
        await db_session.commit()

        tenant_context = MockTenantContext(tenant_id=1)
        service = TemplateService(
            db_manager=MockDBManager(db_session), tenant_context=tenant_context
        )

        # Act: Direct service call
        result = await service.instantiate(
            template.id,
            TemplateInstantiateRequest(template_id=template.id, company_name="Test Tech BV"),
        )

        # Assert: Query database directly
        dept_result = await db_session.execute(
            select(Department).where(Department.company_id == result.id)
        )
        departments = dept_result.scalars().all()

        assert len(departments) == 5
        engineering = next(d for d in departments if d.name == "Engineering")
        assert engineering.board_role == "CTO"
        assert engineering.budget_monthly_tokens == 40000

        # Verify all expected departments exist
        dept_names = {d.name for d in departments}
        expected_names = {"Engineering", "Product", "Sales", "HR", "Finance"}
        assert dept_names == expected_names

    async def test_agents_persisted_with_department_fk(self, db_session: AsyncSession) -> None:
        """
        Direct DB test: Verify agents have department_id FK set.
        """
        # Arrange
        template = CompanyTemplate(
            id=uuid.uuid4(),
            name="Test",
            company_type="mkb",
            sector="Technologie",
            template_definition={"departments": [{"name": "Management"}]},
            is_platform_template=True,
            status="active",
        )
        db_session.add(template)
        await db_session.commit()

        tenant_context = MockTenantContext(tenant_id=1)
        service = TemplateService(
            db_manager=MockDBManager(db_session), tenant_context=tenant_context
        )

        # Act
        result = await service.instantiate(
            template.id, TemplateInstantiateRequest(template_id=template.id, company_name="Test")
        )

        # Assert: Verify agents have department_id
        dept_result = await db_session.execute(
            select(Department).where(Department.company_id == result.id)
        )
        departments = dept_result.scalars().all()

        agent_result = await db_session.execute(
            select(Agent).where(Agent.department_id.in_([d.id for d in departments]))
        )
        agents = agent_result.scalars().all()

        assert len(agents) > 0
        for agent in agents:
            assert agent.department_id is not None
            # Verify agent is linked to a valid department
            dept_ids = [d.id for d in departments]
            assert agent.department_id in dept_ids

    async def test_department_budgets_persisted_correctly(self, db_session: AsyncSession) -> None:
        """
        Direct DB test: Verify budget amounts are correct.
        """
        template = CompanyTemplate(
            id=uuid.uuid4(),
            name="Enterprise Test",
            company_type="enterprise",
            sector="Technologie",
            template_definition={"departments": [{"name": "Management"}]},
            is_platform_template=True,
            status="active",
        )
        db_session.add(template)
        await db_session.commit()

        tenant_context = MockTenantContext(tenant_id=1)
        service = TemplateService(
            db_manager=MockDBManager(db_session), tenant_context=tenant_context
        )

        result = await service.instantiate(
            template.id,
            TemplateInstantiateRequest(template_id=template.id, company_name="Enterprise BV"),
        )

        dept_result = await db_session.execute(
            select(Department).where(Department.company_id == result.id)
        )
        departments = dept_result.scalars().all()

        # Verify C-Level has highest budget
        cto = next(d for d in departments if d.board_role == "CTO")
        cfo = next(d for d in departments if d.board_role == "CFO")

        assert cto.budget_monthly_tokens == 100000
        assert cfo.budget_monthly_tokens == 100000

        # Verify other departments have appropriate budgets
        cpo = next(d for d in departments if d.board_role == "CPO")
        assert cpo.budget_monthly_tokens == 80000

    async def test_horeca_sector_departments_persisted(self, db_session: AsyncSession) -> None:
        """
        Direct DB test: Verify Horeca sector departments are persisted correctly.
        """
        # Arrange: Create Horeca template
        template = CompanyTemplate(
            id=uuid.uuid4(),
            name="Horeca MKB Test",
            company_type="mkb",
            sector="Horeca",
            template_definition={"departments": [{"name": "Management"}]},
            is_platform_template=True,
            status="active",
        )
        db_session.add(template)
        await db_session.commit()

        tenant_context = MockTenantContext(tenant_id=1)
        service = TemplateService(
            db_manager=MockDBManager(db_session), tenant_context=tenant_context
        )

        # Act
        result = await service.instantiate(
            template.id,
            TemplateInstantiateRequest(template_id=template.id, company_name="Test Restaurant"),
        )

        # Assert
        dept_result = await db_session.execute(
            select(Department).where(Department.company_id == result.id)
        )
        departments = dept_result.scalars().all()

        # Horeca MKB has 6 departments
        assert len(departments) == 6

        # Verify Keuken department exists with correct board role
        keuken = next(d for d in departments if d.name == "Keuken")
        assert keuken.board_role == "Executive Chef"
        assert keuken.budget_monthly_tokens == 40000

    async def test_zzp_sector_departments_persisted(self, db_session: AsyncSession) -> None:
        """
        Direct DB test: Verify ZZP sector departments are persisted correctly.
        """
        # Arrange: Create ZZP template
        template = CompanyTemplate(
            id=uuid.uuid4(),
            name="ZZP Test",
            company_type="zzp",
            sector="Technologie",
            template_definition={"departments": [{"name": "Zelfstandig"}]},
            is_platform_template=True,
            status="active",
        )
        db_session.add(template)
        await db_session.commit()

        tenant_context = MockTenantContext(tenant_id=1)
        service = TemplateService(
            db_manager=MockDBManager(db_session), tenant_context=tenant_context
        )

        # Act
        result = await service.instantiate(
            template.id,
            TemplateInstantiateRequest(template_id=template.id, company_name="Freelancer Test"),
        )

        # Assert
        dept_result = await db_session.execute(
            select(Department).where(Department.company_id == result.id)
        )
        departments = dept_result.scalars().all()

        # ZZP Technologie has 3 departments
        assert len(departments) == 3

        # Verify Zelfstandig department
        zelfstandig = next(d for d in departments if d.name == "Zelfstandig")
        assert zelfstandig.board_role == "Founder"
        assert zelfstandig.budget_monthly_tokens == 20000

    async def test_company_persisted_with_template_reference(
        self, db_session: AsyncSession
    ) -> None:
        """
        Direct DB test: Verify company is created with template reference.
        """
        template_id = uuid.uuid4()
        template = CompanyTemplate(
            id=template_id,
            name="Template Test",
            company_type="mkb",
            sector="Consultancy",
            template_definition={"departments": [{"name": "Management"}]},
            is_platform_template=True,
            status="active",
        )
        db_session.add(template)
        await db_session.commit()

        tenant_context = MockTenantContext(tenant_id=1)
        service = TemplateService(
            db_manager=MockDBManager(db_session), tenant_context=tenant_context
        )

        result = await service.instantiate(
            template.id,
            TemplateInstantiateRequest(template_id=template.id, company_name="Consultancy BV"),
        )

        # Query company directly
        company_result = await db_session.execute(select(Company).where(Company.id == result.id))
        company = company_result.scalar_one()

        assert company.name == "Consultancy BV"
        assert company.company_type == "mkb"
        assert company.sector == "Consultancy"
        assert company.template_id == template_id
        assert company.tenant_id == 1

    async def test_template_usage_count_incremented(self, db_session: AsyncSession) -> None:
        """
        Direct DB test: Verify template usage count is incremented on instantiation.
        """
        template = CompanyTemplate(
            id=uuid.uuid4(),
            name="Usage Test Template",
            company_type="mkb",
            sector="Retail",
            template_definition={"departments": [{"name": "Management"}]},
            is_platform_template=True,
            status="active",
            usage_count=5,
        )
        db_session.add(template)
        await db_session.commit()

        tenant_context = MockTenantContext(tenant_id=1)
        service = TemplateService(
            db_manager=MockDBManager(db_session), tenant_context=tenant_context
        )

        # Instantiate twice
        await service.instantiate(
            template.id,
            TemplateInstantiateRequest(template_id=template.id, company_name="Company 1"),
        )
        await db_session.commit()

        await service.instantiate(
            template.id,
            TemplateInstantiateRequest(template_id=template.id, company_name="Company 2"),
        )
        await db_session.commit()

        # Refresh template from DB
        await db_session.refresh(template)

        assert template.usage_count == 7

    async def test_department_customization_persisted(self, db_session: AsyncSession) -> None:
        """
        Direct DB test: Verify department name customizations are persisted.
        """
        template = CompanyTemplate(
            id=uuid.uuid4(),
            name="Customization Test",
            company_type="mkb",
            sector="Technologie",
            template_definition={"departments": [{"name": "Management"}]},
            is_platform_template=True,
            status="active",
        )
        db_session.add(template)
        await db_session.commit()

        tenant_context = MockTenantContext(tenant_id=1)
        service = TemplateService(
            db_manager=MockDBManager(db_session), tenant_context=tenant_context
        )

        # Instantiate with customization
        customizations: dict[str, Any] = {"dept_Engineering_name": "R&D"}
        result = await service.instantiate(
            template.id,
            TemplateInstantiateRequest(
                template_id=template.id,
                company_name="Custom Company",
                customizations=customizations,
            ),
        )

        # Query departments
        dept_result = await db_session.execute(
            select(Department).where(Department.company_id == result.id)
        )
        departments = dept_result.scalars().all()

        # Verify customized name is used
        dept_names = {d.name for d in departments}
        assert "R&D" in dept_names
        assert "Engineering" not in dept_names

        # Verify other departments still exist
        assert "Product" in dept_names
