"""Tests for TemplateService sector enrichment functionality.

These tests verify that templates are properly enriched with sector-specific
department configurations during instantiation.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.company.models import Company, CompanyTemplate, Department
from src.core.company.template_service import TemplateService


@pytest.fixture
def mock_tenant_context():
    """Create mock tenant context."""
    context = MagicMock()
    context.tenant_id = 1
    return context


@pytest.fixture
def mock_db_manager():
    """Create mock database manager."""
    manager = MagicMock()
    manager.get_session = MagicMock()
    return manager


@pytest.fixture
def template_service(mock_db_manager, mock_tenant_context):
    """Create TemplateService instance with mocked dependencies."""
    return TemplateService(mock_db_manager, mock_tenant_context)


@pytest.mark.asyncio
async def test_user_instantiating_technology_template_gets_proper_departments(
    template_service,
):
    """E2E: User instantiates Technologie MKB template -> sees 5 departments."""
    # Arrange
    template = MagicMock()
    template.sector = "Technologie"
    template.company_type = "mkb"
    template.template_definition = {
        "departments": [
            {"name": "Algemeen Management", "type": "management"},
            {"name": "Operations", "type": "operations"},
        ]
    }

    company = MagicMock()
    company.id = uuid.uuid4()
    company.tenant_id = 1

    # Create mock session that returns our created departments
    mock_session = AsyncMock()
    created_depts = []

    async def mock_flush():
        # Simulate department creation with IDs
        for dept in created_depts:
            if not hasattr(dept, "id") or dept.id is None:
                dept.id = uuid.uuid4()

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_depts.append(x)

    # Act
    departments = await template_service._create_departments_from_template(
        mock_session, company, template, {}
    )

    # Assert: User gets 5 enriched departments
    assert len(departments) == 5
    dept_names = [d.name for d in departments]
    assert "Engineering" in dept_names
    assert "Product" in dept_names
    assert "Sales" in dept_names
    assert "HR" in dept_names
    assert "Finance" in dept_names

    # Check board roles
    engineering = next(d for d in departments if d.name == "Engineering")
    assert engineering.board_role == "CTO"
    assert engineering.budget_monthly_tokens == 40000

    # Check other departments have correct board roles
    product = next(d for d in departments if d.name == "Product")
    assert product.board_role == "CPO"
    assert product.budget_monthly_tokens == 35000


@pytest.mark.asyncio
async def test_user_instantiating_horeca_template_gets_kitchen_department(
    template_service,
):
    """E2E: User instantiates Horeca template -> sees Keuken."""
    template = MagicMock()
    template.sector = "Horeca"
    template.company_type = "mkb"
    template.template_definition = {"departments": [{"name": "Management"}]}

    company = MagicMock()
    company.id = uuid.uuid4()
    company.tenant_id = 1

    mock_session = AsyncMock()
    created_depts = []

    async def mock_flush():
        for dept in created_depts:
            if not hasattr(dept, "id") or dept.id is None:
                dept.id = uuid.uuid4()

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_depts.append(x)

    departments = await template_service._create_departments_from_template(
        mock_session, company, template, {}
    )

    # Assert: User gets Horeca-specific departments including Keuken
    dept_names = [d.name for d in departments]
    assert "Keuken" in dept_names
    assert "Bediening" in dept_names
    assert "Bar" in dept_names

    # Check Keuken has proper board role
    keuken = next(d for d in departments if d.name == "Keuken")
    assert keuken.board_role == "Executive Chef"


@pytest.mark.asyncio
async def test_sector_specific_template_not_overridden(template_service):
    """Test that templates with sector-specific departments are not overridden."""
    template = MagicMock()
    template.sector = "Technologie"
    template.company_type = "mkb"
    # Template already has sector-specific departments
    template.template_definition = {
        "departments": [
            {"name": "Engineering", "board_role": "VP Eng", "budget_monthly_tokens": 50000},
            {"name": "Sales", "board_role": "Sales Director", "budget_monthly_tokens": 40000},
        ]
    }

    company = MagicMock()
    company.id = uuid.uuid4()
    company.tenant_id = 1

    mock_session = AsyncMock()
    created_depts = []

    async def mock_flush():
        for dept in created_depts:
            if not hasattr(dept, "id") or dept.id is None:
                dept.id = uuid.uuid4()

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_depts.append(x)

    departments = await template_service._create_departments_from_template(
        mock_session, company, template, {}
    )

    # Assert: Original template departments are preserved
    assert len(departments) == 2
    dept_names = [d.name for d in departments]
    assert "Engineering" in dept_names
    assert "Sales" in dept_names

    # Verify the custom values are preserved
    eng = next(d for d in departments if d.name == "Engineering")
    assert eng.board_role == "VP Eng"
    assert eng.budget_monthly_tokens == 50000


@pytest.mark.asyncio
async def test_customizations_applied_to_enriched_departments(template_service):
    """Test that user customizations are applied to enriched departments."""
    template = MagicMock()
    template.sector = "Technologie"
    template.company_type = "mkb"
    template.template_definition = {"departments": [{"name": "Management"}]}

    company = MagicMock()
    company.id = uuid.uuid4()
    company.tenant_id = 1

    mock_session = AsyncMock()
    created_depts = []

    async def mock_flush():
        for dept in created_depts:
            if not hasattr(dept, "id") or dept.id is None:
                dept.id = uuid.uuid4()

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_depts.append(x)

    # User wants to rename Engineering to "Product Development"
    customizations = {"dept_Engineering_name": "Product Development"}

    departments = await template_service._create_departments_from_template(
        mock_session, company, template, customizations
    )

    # Assert: Custom name is applied
    dept_names = [d.name for d in departments]
    assert "Product Development" in dept_names
    assert "Engineering" not in dept_names

    # Other departments should still be present
    assert "Product" in dept_names
    assert "Sales" in dept_names


@pytest.mark.asyncio
async def test_unknown_sector_returns_original_departments(template_service):
    """Test that unknown sectors don't break - returns original departments."""
    template = MagicMock()
    template.sector = "UnknownSector"
    template.company_type = "mkb"
    template.template_definition = {
        "departments": [
            {"name": "Management", "board_role": "CEO"},
            {"name": "Operations", "board_role": "COO"},
        ]
    }

    company = MagicMock()
    company.id = uuid.uuid4()
    company.tenant_id = 1

    mock_session = AsyncMock()
    created_depts = []

    async def mock_flush():
        for dept in created_depts:
            if not hasattr(dept, "id") or dept.id is None:
                dept.id = uuid.uuid4()

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_depts.append(x)

    departments = await template_service._create_departments_from_template(
        mock_session, company, template, {}
    )

    # Assert: Original departments preserved when sector not found
    assert len(departments) == 2
    dept_names = [d.name for d in departments]
    assert "Management" in dept_names
    assert "Operations" in dept_names


@pytest.mark.asyncio
async def test_enterprise_size_gets_more_departments(template_service):
    """Test that enterprise companies get more departments than MKB."""
    template = MagicMock()
    template.sector = "Technologie"
    template.company_type = "enterprise"
    template.template_definition = {"departments": [{"name": "Management"}]}

    company = MagicMock()
    company.id = uuid.uuid4()
    company.tenant_id = 1

    mock_session = AsyncMock()
    created_depts = []

    async def mock_flush():
        for dept in created_depts:
            if not hasattr(dept, "id") or dept.id is None:
                dept.id = uuid.uuid4()

    mock_session.flush = mock_flush
    mock_session.add = lambda x: created_depts.append(x)

    departments = await template_service._create_departments_from_template(
        mock_session, company, template, {}
    )

    # Assert: Enterprise gets 9 departments for Technologie
    assert len(departments) == 9

    # Should include enterprise-specific departments
    dept_names = [d.name for d in departments]
    assert "Security" in dept_names
    assert "Data Science" in dept_names
    assert "Legal" in dept_names

    # Check higher budgets for enterprise
    eng = next(d for d in departments if d.name == "Engineering")
    assert eng.budget_monthly_tokens == 100000
