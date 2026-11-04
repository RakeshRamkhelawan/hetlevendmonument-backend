"""Integration tests for template instantiation with real HTTP calls.

These tests verify the complete flow:
1. Create template in database
2. Call API endpoint with real HTTP request
3. Verify response
4. Query database to verify departments and agents created
"""

import uuid
from typing import Any, Dict, List

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.models import Agent
from src.core.company.models import CompanyTemplate, Department


@pytest.mark.integration
@pytest.mark.asyncio
class TestTemplateInstantiationIntegration:
    """Real API integration tests for template enrichment."""

    async def test_instantiate_technology_template_creates_departments_and_agents(
        self, client: AsyncClient, db_session: AsyncSession, admin_auth_headers: Dict[str, str]
    ) -> None:
        """
        E2E: POST /api/v1/templates/{id}/instantiate

        Given: A Technology MKB template exists
        When: User calls instantiate endpoint
        Then: Response is 201 with company data
        And: 5 departments created in database
        And: Agents created for each department
        """
        # Arrange: Create template in database
        template = await create_template_in_db(
            db_session,
            sector="Technologie",
            company_type="mkb",
            template_definition={"departments": [{"name": "Management", "type": "management"}]},
        )

        # Act: Real HTTP POST request
        response = await client.post(
            f"/api/v1/templates/{template.id}/instantiate",
            json={
                "template_id": str(template.id),
                "company_name": "Acme Tech BV",
                "customizations": {},
            },
            headers=admin_auth_headers,
        )

        # Assert: HTTP 201 Created
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Acme Tech BV"
        company_id = data["id"]

        # Assert: Query database for departments
        departments = await get_departments_from_db(db_session, uuid.UUID(company_id))
        assert len(departments) == 5
        dept_names = [d.name for d in departments]
        assert "Engineering" in dept_names
        assert "Product" in dept_names
        assert "Sales" in dept_names
        assert "HR" in dept_names
        assert "Finance" in dept_names

        # Assert: Engineering has correct board role
        engineering = next(d for d in departments if d.name == "Engineering")
        assert engineering.board_role == "CTO"
        assert engineering.budget_monthly_tokens == 40000

        # Assert: Agents created
        agents = await get_agents_from_db(db_session, departments)
        # Engineering has 4 agents, others have varying amounts
        engineering_agents = await get_agents_for_department(db_session, engineering.id)
        assert len(engineering_agents) >= 4  # At least 4 agents for Engineering

    async def test_instantiate_horeca_template_creates_kitchen_department(
        self, client: AsyncClient, db_session: AsyncSession, admin_auth_headers: Dict[str, str]
    ) -> None:
        """
        E2E: Horeca template instantiation

        Given: A Horeca MKB template exists
        When: User instantiates template
        Then: Keuken department created with Executive Chef role
        And: Kitchen agents created (Sous Chef, Line Cook, etc.)
        """
        # Arrange
        template = await create_template_in_db(
            db_session,
            sector="Horeca",
            company_type="mkb",
            template_definition={"departments": [{"name": "Management"}]},
        )

        # Act
        response = await client.post(
            f"/api/v1/templates/{template.id}/instantiate",
            json={
                "template_id": str(template.id),
                "company_name": "Restaurant De Gouden Lepel",
                "customizations": {},
            },
            headers=admin_auth_headers,
        )

        # Assert HTTP
        assert response.status_code == 201
        company_id = uuid.UUID(response.json()["id"])

        # Assert Database
        departments = await get_departments_from_db(db_session, company_id)
        dept_names = [d.name for d in departments]
        assert "Keuken" in dept_names
        assert "Bediening" in dept_names

        keuken = next(d for d in departments if d.name == "Keuken")
        assert keuken.board_role == "Executive Chef"

        # Assert Kitchen agents were created
        kitchen_agents = await get_agents_for_department(db_session, keuken.id)
        agent_names = [a.name for a in kitchen_agents]
        assert "Sous Chef" in agent_names
        assert "Line Cook" in agent_names
        assert "Pastry Chef" in agent_names

    async def test_instantiate_enterprise_template_gets_more_departments(
        self, client: AsyncClient, db_session: AsyncSession, admin_auth_headers: Dict[str, str]
    ) -> None:
        """
        E2E: Enterprise template gets 9 departments vs 5 for MKB
        """
        template = await create_template_in_db(
            db_session,
            sector="Technologie",
            company_type="enterprise",
            template_definition={"departments": [{"name": "Management"}]},
        )

        response = await client.post(
            f"/api/v1/templates/{template.id}/instantiate",
            json={
                "template_id": str(template.id),
                "company_name": "Big Tech Corp",
                "customizations": {},
            },
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        company_id = uuid.UUID(response.json()["id"])

        departments = await get_departments_from_db(db_session, company_id)
        assert len(departments) == 9  # Enterprise has 9 departments

        # Verify enterprise-specific departments exist
        dept_names = [d.name for d in departments]
        assert "Engineering" in dept_names
        assert "Security" in dept_names  # Only in enterprise
        assert "Data Science" in dept_names  # Only in enterprise
        assert "Legal" in dept_names  # Only in enterprise

    async def test_instantiate_unknown_sector_returns_original_departments(
        self, client: AsyncClient, db_session: AsyncSession, admin_auth_headers: Dict[str, str]
    ) -> None:
        """
        E2E: Unknown sector gracefully falls back to original departments
        """
        template = await create_template_in_db(
            db_session,
            sector="UnknownSector",
            company_type="mkb",
            template_definition={
                "departments": [
                    {
                        "name": "Custom Dept",
                        "board_role": "Custom Role",
                        "budget_monthly_tokens": 25000,
                    }
                ]
            },
        )

        response = await client.post(
            f"/api/v1/templates/{template.id}/instantiate",
            json={
                "template_id": str(template.id),
                "company_name": "Custom Company",
                "customizations": {},
            },
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        company_id = uuid.UUID(response.json()["id"])

        departments = await get_departments_from_db(db_session, company_id)
        assert len(departments) == 1
        assert departments[0].name == "Custom Dept"
        assert departments[0].board_role == "Custom Role"

    async def test_instantiate_with_customizations_applied(
        self, client: AsyncClient, db_session: AsyncSession, admin_auth_headers: Dict[str, str]
    ) -> None:
        """
        E2E: User customizations are applied to enriched departments
        """
        template = await create_template_in_db(
            db_session,
            sector="Technologie",
            company_type="mkb",
            template_definition={"departments": [{"name": "Management"}]},
        )

        response = await client.post(
            f"/api/v1/templates/{template.id}/instantiate",
            json={
                "template_id": str(template.id),
                "company_name": "Tech BV",
                "customizations": {"dept_Engineering_name": "R&D"},
            },
            headers=admin_auth_headers,
        )

        assert response.status_code == 201
        company_id = uuid.UUID(response.json()["id"])

        departments = await get_departments_from_db(db_session, company_id)
        dept_names = [d.name for d in departments]
        assert "R&D" in dept_names  # Customized name
        assert "Engineering" not in dept_names

        # Verify R&D has the same board role as Engineering would have
        rd_dept = next(d for d in departments if d.name == "R&D")
        assert rd_dept.board_role == "CTO"

    async def test_instantiate_returns_404_for_nonexistent_template(
        self, client: AsyncClient, admin_auth_headers: Dict[str, str]
    ) -> None:
        """
        E2E: Requesting instantiation of non-existent template returns 404
        """
        fake_uuid = str(uuid.uuid4())

        response = await client.post(
            f"/api/v1/templates/{fake_uuid}/instantiate",
            json={
                "template_id": fake_uuid,
                "company_name": "Test Company",
                "customizations": {},
            },
            headers=admin_auth_headers,
        )

        assert response.status_code == 404

    async def test_instantize_validates_company_name_length(
        self, client: AsyncClient, db_session: AsyncSession, admin_auth_headers: Dict[str, str]
    ) -> None:
        """
        E2E: Company name must be between 2 and 100 characters
        """
        template = await create_template_in_db(
            db_session,
            sector="Technologie",
            company_type="mkb",
            template_definition={"departments": [{"name": "Management"}]},
        )

        # Test with name too short
        response = await client.post(
            f"/api/v1/templates/{template.id}/instantiate",
            json={
                "template_id": str(template.id),
                "company_name": "A",
                "customizations": {},
            },
            headers=admin_auth_headers,
        )

        assert response.status_code == 422  # Validation error


# Helper functions


async def create_template_in_db(
    session: AsyncSession,
    sector: str,
    company_type: str,
    template_definition: Dict[str, Any],
) -> CompanyTemplate:
    """Helper to create a template in the database."""
    template = CompanyTemplate(
        id=uuid.uuid4(),
        name=f"Test {sector} {company_type}",
        company_type=company_type,
        sector=sector,
        description="Test template for integration tests",
        template_definition=template_definition,
        is_platform_template=True,
        status="active",
        usage_count=0,
        rating_sum=0,
        rating_count=0,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


async def get_departments_from_db(session: AsyncSession, company_id: uuid.UUID) -> List[Department]:
    """Helper to query departments from database."""
    result = await session.execute(select(Department).where(Department.company_id == company_id))
    return list(result.scalars().all())


async def get_agents_from_db(session: AsyncSession, departments: List[Department]) -> List[Agent]:
    """Helper to query agents for departments."""
    dept_ids = [d.id for d in departments]
    result = await session.execute(select(Agent).where(Agent.department_id.in_(dept_ids)))
    return list(result.scalars().all())


async def get_agents_for_department(session: AsyncSession, department_id: uuid.UUID) -> List[Agent]:
    """Helper to query agents for a specific department."""
    result = await session.execute(select(Agent).where(Agent.department_id == department_id))
    return list(result.scalars().all())
