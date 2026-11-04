"""Tests for CompanyService - Taak 2.1

TDD tests for company CRUD operations.
"""

import uuid
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.company.company_service import CompanyService
from src.core.company.models import Company
from src.core.company.schemas import CompanyCreate, CompanyUpdate

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db_manager():
    """Mock DatabaseManager."""
    manager = MagicMock()
    manager.get_session = MagicMock()
    return manager


@pytest.fixture
def mock_tenant_context():
    """Mock TenantContext."""
    context = MagicMock()
    context.get_tenant_id = Mock(return_value=1)
    return context


@pytest.fixture
def company_service(mock_db_manager, mock_tenant_context):
    """Create CompanyService with mocked dependencies."""
    return CompanyService(
        db_manager=mock_db_manager,
        tenant_context=mock_tenant_context,
    )


def create_mock_company(company_id=None, name="Test Company", **kwargs):
    """Create a mock company with concrete values for Pydantic validation."""
    mock = MagicMock(spec=Company)
    mock.id = company_id or uuid.uuid4()
    mock.name = name
    mock.company_type = kwargs.get("company_type", "mkb")
    mock.sector = kwargs.get("sector", "technology")
    mock.mission = kwargs.get("mission", None)
    mock.tenant_id = kwargs.get("tenant_id", 1)
    mock.status = kwargs.get("status", "active")
    mock.created_at = kwargs.get("created_at", datetime.utcnow())
    mock.config = kwargs.get("config", {})
    mock.board_role_config = kwargs.get("board_role_config", None)
    mock.template_id = kwargs.get("template_id", None)
    return mock


@pytest.fixture
def mock_session():
    """Mock AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


# ============================================================================
# Happy Path Tests
# ============================================================================


class TestCompanyServiceHappyPath:
    """Happy path tests for CompanyService."""

    async def test_create_company(self, company_service, mock_db_manager, mock_session):
        """Create company successfully."""
        # Setup mock session context manager
        mock_db_manager.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        data = CompanyCreate(
            name="Test Company",
            company_type="mkb",
            sector="technology",
        )

        # Mock the company that will be created with proper values after refresh
        mock_company = create_mock_company(
            name="Test Company", company_type="mkb", sector="technology"
        )

        # Capture the company object passed to session.add and set its values
        def capture_add(obj):
            # Copy values from mock_company to the actual object
            obj.id = mock_company.id
            obj.name = mock_company.name
            obj.company_type = mock_company.company_type
            obj.sector = mock_company.sector
            obj.tenant_id = mock_company.tenant_id
            obj.status = mock_company.status
            obj.created_at = mock_company.created_at
            return None

        mock_session.add = MagicMock(side_effect=capture_add)
        mock_session.refresh = AsyncMock()

        response = await company_service.create_company(data)

        assert response.name == "Test Company"
        assert response.company_type == "mkb"
        assert response.sector == "technology"
        assert response.tenant_id == 1

    async def test_get_company(self, company_service, mock_db_manager, mock_session):
        """Get company by ID."""
        mock_db_manager.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock query result with concrete values
        company_id = uuid.uuid4()
        mock_company = create_mock_company(company_id=company_id, name="Test Company")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_company
        mock_session.execute.return_value = mock_result

        response = await company_service.get_company(company_id)

        assert response is not None
        assert response.name == "Test Company"

    async def test_list_companies(self, company_service, mock_db_manager, mock_session):
        """List companies for tenant."""
        mock_db_manager.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        # Mock companies query with concrete values
        mock_company = create_mock_company(name="Company 1")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_company]
        mock_session.execute.return_value = mock_result

        response = await company_service.list_companies()

        assert response.total == 1
        assert len(response.companies) == 1
        assert response.companies[0].name == "Company 1"

    async def test_update_company(self, company_service, mock_db_manager, mock_session):
        """Update company name."""
        mock_db_manager.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        company_id = uuid.uuid4()
        mock_company = create_mock_company(company_id=company_id, name="Old Name")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_company
        mock_session.execute.return_value = mock_result

        data = CompanyUpdate(name="New Name")

        response = await company_service.update_company(company_id, data)

        assert response is not None
        assert mock_company.name == "New Name"

    async def test_delete_company_soft(self, company_service, mock_db_manager, mock_session):
        """Soft delete company."""
        mock_db_manager.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        company_id = uuid.uuid4()
        mock_company = MagicMock(spec=Company)
        mock_company.id = company_id
        mock_company.status = "active"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_company
        mock_session.execute.return_value = mock_result

        result = await company_service.delete_company(company_id)

        assert result is True
        assert mock_company.status == "deleted"

    async def test_export_template(self, company_service, mock_db_manager, mock_session):
        """Export company as template."""
        mock_db_manager.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        company_id = uuid.uuid4()
        mock_company = MagicMock(spec=Company)
        mock_company.id = company_id
        mock_company.name = "Test Company"
        mock_company.company_type = "mkb"
        mock_company.sector = "technology"
        mock_company.mission = "Our mission"
        mock_company.config = {"key": "value"}
        mock_company.board_role_config = None
        mock_company.tenant_id = 1
        mock_company.status = "active"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_company
        mock_session.execute.return_value = mock_result

        template = await company_service.export_as_template(company_id)

        assert template is not None
        assert template["name"] == "Test Company Template"
        assert template["company_type"] == "mkb"
        assert "departments" in template
        assert "goals" in template


# ============================================================================
# Unhappy Path Tests
# ============================================================================


class TestCompanyServiceUnhappyPath:
    """Unhappy path tests for CompanyService."""

    async def test_get_company_not_found(self, company_service, mock_db_manager, mock_session):
        """Get non-existent company returns None."""
        mock_db_manager.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        company_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        response = await company_service.get_company(company_id)

        assert response is None

    async def test_get_company_wrong_tenant(self, company_service, mock_db_manager, mock_session):
        """Company from other tenant not visible."""
        mock_db_manager.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        company_id = uuid.uuid4()

        # Simulate tenant isolation - no company found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        response = await company_service.get_company(company_id)

        assert response is None

    async def test_update_company_not_found(self, company_service, mock_db_manager, mock_session):
        """Update non-existent company returns None."""
        mock_db_manager.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        company_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = CompanyUpdate(name="New Name")

        response = await company_service.update_company(company_id, data)

        assert response is None

    async def test_delete_company_not_found(self, company_service, mock_db_manager, mock_session):
        """Delete non-existent company returns False."""
        mock_db_manager.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        company_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await company_service.delete_company(company_id)

        assert result is False

    async def test_delete_company_already_deleted(
        self, company_service, mock_db_manager, mock_session
    ):
        """Delete already deleted company returns False."""
        mock_db_manager.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        company_id = uuid.uuid4()

        # Already deleted company not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await company_service.delete_company(company_id)

        assert result is False

    async def test_create_company_no_tenant(self, mock_db_manager):
        """Create company without tenant context raises error."""
        # Setup context with no tenant
        mock_context = MagicMock()
        mock_context.tenant_id = None

        service = CompanyService(
            db_manager=mock_db_manager,
            tenant_context=mock_context,
        )

        data = CompanyCreate(
            name="Test Company",
            company_type="mkb",
            sector="technology",
        )

        with pytest.raises(ValueError, match="Tenant context required"):
            await service.create_company(data)


# ============================================================================
# Integration-style Tests
# ============================================================================


class TestCompanyServiceIntegration:
    """Integration-style tests with real database session mocking."""

    async def test_company_lifecycle(self, company_service, mock_db_manager, mock_session):
        """Full lifecycle: create → get → update → delete."""
        mock_db_manager.get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_db_manager.get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        company_id = uuid.uuid4()

        # Create mock with concrete values
        mock_company = create_mock_company(company_id=company_id, name="Test Company")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_company
        mock_session.execute.return_value = mock_result

        # Get
        response = await company_service.get_company(company_id)
        assert response is not None
        assert response.name == "Test Company"

        # Update
        data = CompanyUpdate(name="Updated Name")
        response = await company_service.update_company(company_id, data)
        assert response is not None

        # Delete
        result = await company_service.delete_company(company_id)
        assert result is True
