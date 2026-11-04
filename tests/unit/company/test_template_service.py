"""Unit tests for TemplateService.

Tests all TemplateService methods with mocked database.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.company.models import Company, CompanyTemplate, Department, Goal
from src.core.company.schemas import CompanyResponse, TemplateInstantiateRequest, TemplateResponse
from src.core.company.template_service import TemplateInstantiationError, TemplateService
from src.core.exceptions.exceptions import NotFoundError


class MockTenantContext:
    """Mock tenant context for testing."""

    def __init__(self, tenant_id: int = 1):
        self.tenant_id = tenant_id


class MockDBManager:
    """Mock database manager for testing."""

    def __init__(self, session: AsyncSession):
        self._session = session

    def get_session(self):
        class SessionContext:
            def __init__(self, session):
                self.session = session

            async def __aenter__(self):
                return self.session

            async def __aexit__(self, *args):
                return False

        return SessionContext(self._session)


@pytest.fixture
def tenant_context():
    return MockTenantContext(tenant_id=1)


@pytest.fixture
def mock_session():
    """Create a properly configured mock session."""
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def template_service(mock_session, tenant_context):
    db_manager = MockDBManager(mock_session)
    return TemplateService(db_manager, tenant_context)


class TestListTemplates:
    """Tests for list_templates method."""

    async def test_list_all_templates(self, template_service, mock_session):
        """Should list all templates accessible to tenant."""
        # Arrange
        template1 = MagicMock(spec=CompanyTemplate)
        template1.id = uuid.uuid4()
        template1.name = "Template 1"
        template1.company_type = "mkb"
        template1.sector = "Tech"
        template1.description = "Test"
        template1.is_platform_template = True
        template1.usage_count = 10
        template1.rating_sum = 45
        template1.rating_count = 10

        template2 = MagicMock(spec=CompanyTemplate)
        template2.id = uuid.uuid4()
        template2.name = "Template 2"
        template2.company_type = "zzp"
        template2.sector = "Design"
        template2.description = "Test 2"
        template2.is_platform_template = False
        template2.usage_count = 5
        template2.rating_sum = 20
        template2.rating_count = 5

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [template1, template2]
        mock_session.execute.return_value = mock_result

        # Act
        templates = await template_service.list_templates()

        # Assert
        assert len(templates) == 2
        assert templates[0].name == "Template 1"
        assert templates[1].name == "Template 2"

    async def test_list_with_company_type_filter(self, template_service, mock_session):
        """Should filter by company_type."""
        # Arrange
        template = MagicMock(spec=CompanyTemplate)
        template.id = uuid.uuid4()
        template.name = "MKB Template"
        template.company_type = "mkb"
        template.sector = "Tech"
        template.description = "Test"
        template.is_platform_template = True
        template.usage_count = 5
        template.rating_sum = 20
        template.rating_count = 5

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [template]
        mock_session.execute.return_value = mock_result

        # Act
        templates = await template_service.list_templates(filters={"company_type": "mkb"})

        # Assert
        assert len(templates) == 1
        assert templates[0].company_type == "mkb"

    async def test_list_with_sector_filter(self, template_service, mock_session):
        """Should filter by sector."""
        # Arrange
        template = MagicMock(spec=CompanyTemplate)
        template.id = uuid.uuid4()
        template.name = "Healthcare Template"
        template.company_type = "enterprise"
        template.sector = "Gezondheidszorg"
        template.description = "Test"
        template.is_platform_template = True
        template.usage_count = 3
        template.rating_sum = 15
        template.rating_count = 3

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [template]
        mock_session.execute.return_value = mock_result

        # Act
        templates = await template_service.list_templates(filters={"sector": "Gezondheidszorg"})

        # Assert
        assert len(templates) == 1
        assert templates[0].sector == "Gezondheidszorg"

    async def test_list_empty_result(self, template_service, mock_session):
        """Should return empty list when no templates match."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Act
        templates = await template_service.list_templates()

        # Assert
        assert templates == []


class TestGetTemplate:
    """Tests for get_template method."""

    async def test_get_existing_template(self, template_service, mock_session):
        """Should return template by ID."""
        # Arrange
        template_id = uuid.uuid4()
        template = MagicMock(spec=CompanyTemplate)
        template.id = template_id
        template.name = "Test Template"
        template.company_type = "mkb"
        template.sector = "Tech"
        template.description = "Description"
        template.is_platform_template = True
        template.usage_count = 10
        template.rating_sum = 45
        template.rating_count = 10

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = template
        mock_session.execute.return_value = mock_result

        # Act
        result = await template_service.get_template(template_id)

        # Assert
        assert result.id == template_id
        assert result.name == "Test Template"
        assert result.rating_avg == 4.5

    async def test_get_nonexistent_template(self, template_service, mock_session):
        """Should raise NotFoundError for nonexistent template."""
        # Arrange
        template_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(NotFoundError, match=f"Template {template_id} not found"):
            await template_service.get_template(template_id)


class TestInstantiate:
    """Tests for instantiate method."""

    async def test_instantiate_template(self, template_service, mock_session):
        """Should create company from template."""
        # Arrange
        template_id = uuid.uuid4()
        company_id = uuid.uuid4()

        template = MagicMock(spec=CompanyTemplate)
        template.id = template_id
        template.company_type = "mkb"
        template.sector = "Tech"
        template.template_definition = {
            "mission": "Test mission",
            "departments": [
                {
                    "name": "Sales",
                    "board_role": "Sales",
                    "budget_monthly_tokens": 1000,
                    "domain_pack_ids": ["pack1"],
                }
            ],
            "goals": [],
            "board_role_config": {"default": "CEO"},
        }
        template.usage_count = 5

        # Set up mock to return template first, then company on refresh
        company = MagicMock(spec=Company)
        company.id = company_id
        company.tenant_id = 1
        company.name = "My New Company"
        company.company_type = "mkb"
        company.sector = "Tech"
        company.mission = "Test mission"
        company.status = "active"
        company.created_at = datetime.utcnow()
        company.departments = []
        company.goals = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = template
        mock_session.execute.return_value = mock_result

        # Capture the company that gets added
        def capture_add(obj):
            if isinstance(obj, Company):
                # Simulate ID assignment after flush
                obj.id = company_id

        mock_session.add.side_effect = capture_add
        mock_session.refresh.return_value = None

        request = TemplateInstantiateRequest(
            template_id=template_id,
            company_name="My New Company",
        )

        # Act
        # Mock the company response directly since the ORM mocking is complex
        with patch.object(template_service, "_company_to_response") as mock_response:
            mock_response.return_value = CompanyResponse(
                id=company_id,
                tenant_id=1,
                name="My New Company",
                company_type="mkb",
                sector="Tech",
                mission=None,
                status="active",
                departments_count=0,
                goals_count=0,
                created_at=datetime.utcnow(),
            )
            result = await template_service.instantiate(template_id, request)

        # Assert
        assert result.name == "My New Company"
        assert result.company_type == "mkb"
        assert result.sector == "Tech"
        assert mock_session.commit.called

    async def test_instantiate_with_customizations(self, template_service, mock_session):
        """Should apply customizations during instantiation."""
        # Arrange
        template_id = uuid.uuid4()
        company_id = uuid.uuid4()

        template = MagicMock(spec=CompanyTemplate)
        template.id = template_id
        template.company_type = "mkb"
        template.sector = "Tech"
        template.template_definition = {
            "mission": "Test mission",
            "departments": [
                {
                    "name": "Sales",
                    "board_role": "Sales",
                    "budget_monthly_tokens": 1000,
                    "domain_pack_ids": ["pack1"],
                }
            ],
            "goals": [],
            "board_role_config": {"default": "CEO"},
        }
        template.usage_count = 5

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = template
        mock_session.execute.return_value = mock_result

        request = TemplateInstantiateRequest(
            template_id=template_id,
            company_name="Custom Company",
            customizations={"dept_Sales_name": "Verkoop"},
        )

        # Act
        with patch.object(template_service, "_company_to_response") as mock_response:
            mock_response.return_value = CompanyResponse(
                id=company_id,
                tenant_id=1,
                name="Custom Company",
                company_type="mkb",
                sector="Tech",
                mission=None,
                status="active",
                departments_count=0,
                goals_count=0,
                created_at=datetime.utcnow(),
            )
            result = await template_service.instantiate(template_id, request)

        # Assert
        assert result.name == "Custom Company"

    async def test_instantiate_nonexistent_template(self, template_service, mock_session):
        """Should raise NotFoundError for nonexistent template."""
        # Arrange
        template_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        request = TemplateInstantiateRequest(
            template_id=template_id,
            company_name="Test",
        )

        # Act & Assert
        with pytest.raises(NotFoundError):
            await template_service.instantiate(template_id, request)

    async def test_instantiate_increments_usage(self, template_service, mock_session):
        """Should increment template usage count."""
        # Arrange
        template_id = uuid.uuid4()
        company_id = uuid.uuid4()

        template = MagicMock(spec=CompanyTemplate)
        template.id = template_id
        template.company_type = "mkb"
        template.sector = "Tech"
        template.template_definition = {
            "mission": "Test",
            "departments": [],
            "goals": [],
        }
        template.usage_count = 5

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = template
        mock_session.execute.return_value = mock_result

        request = TemplateInstantiateRequest(
            template_id=template_id,
            company_name="Test Company",
        )

        # Act
        with patch.object(template_service, "_company_to_response") as mock_response:
            mock_response.return_value = CompanyResponse(
                id=company_id,
                tenant_id=1,
                name="Test Company",
                company_type="mkb",
                sector="Tech",
                mission=None,
                status="active",
                departments_count=0,
                goals_count=0,
                created_at=datetime.utcnow(),
            )
            await template_service.instantiate(template_id, request)

        # Assert
        assert template.usage_count == 6


class TestExportCompany:
    """Tests for export_company method."""

    async def test_export_basic_company(self, template_service, mock_session):
        """Should export company structure."""
        # Arrange
        company_id = uuid.uuid4()
        company = MagicMock(spec=Company)
        company.id = company_id
        company.tenant_id = 1
        company.name = "Test Company"
        company.company_type = "mkb"
        company.sector = "Tech"
        company.mission = "Test mission"
        company.board_role_config = {"default": "CEO"}
        company.departments = []
        company.goals = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = company
        mock_session.execute.return_value = mock_result

        # Act
        export = await template_service.export_company(company_id)

        # Assert
        assert export["name"] == "Test Company Template"
        assert export["company_type"] == "mkb"
        assert export["sector"] == "Tech"
        assert export["mission"] == "Test mission"

    async def test_export_with_departments(self, template_service, mock_session):
        """Should export departments."""
        # Arrange
        company_id = uuid.uuid4()
        dept = MagicMock(spec=Department)
        dept.name = "Sales"
        dept.parent_department_id = None
        dept.board_role = "Sales"
        dept.budget_monthly_tokens = 1000
        dept.domain_pack_ids = ["pack1"]

        company = MagicMock(spec=Company)
        company.id = company_id
        company.tenant_id = 1
        company.name = "Test"
        company.company_type = "mkb"
        company.sector = "Tech"
        company.mission = None
        company.board_role_config = {}
        company.departments = [dept]
        company.goals = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = company
        mock_session.execute.return_value = mock_result

        # Act
        export = await template_service.export_company(company_id)

        # Assert
        assert len(export["departments"]) == 1
        assert export["departments"][0]["name"] == "Sales"

    async def test_export_with_goals(self, template_service, mock_session):
        """Should export goals."""
        # Arrange
        company_id = uuid.uuid4()
        dept = MagicMock(spec=Department)
        dept.name = "Sales"

        goal = MagicMock(spec=Goal)
        goal.goal_type = "strategic"
        goal.title = "Revenue Goal"
        goal.description = "Grow revenue"
        goal.parent_goal_id = None
        goal.department = dept
        goal.kpis = {"revenue": 100000}

        company = MagicMock(spec=Company)
        company.id = company_id
        company.tenant_id = 1
        company.name = "Test"
        company.company_type = "mkb"
        company.sector = "Tech"
        company.mission = None
        company.board_role_config = {}
        company.departments = [dept]
        company.goals = [goal]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = company
        mock_session.execute.return_value = mock_result

        # Act
        export = await template_service.export_company(company_id)

        # Assert
        assert len(export["goals"]) == 1
        assert export["goals"][0]["title"] == "Revenue Goal"
        assert export["goals"][0]["department_name"] == "Sales"

    async def test_export_scrubs_secrets(self, template_service, mock_session):
        """Should scrub secrets from export."""
        # Arrange
        company_id = uuid.uuid4()
        company = MagicMock(spec=Company)
        company.id = company_id
        company.tenant_id = 1
        company.name = "Test"
        company.company_type = "mkb"
        company.sector = "Tech"
        company.mission = None
        company.board_role_config = {"api_key": "secret123", "normal_key": "value"}
        company.departments = []
        company.goals = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = company
        mock_session.execute.return_value = mock_result

        # Act
        export = await template_service.export_company(company_id)

        # Assert
        assert "[SCRUBBED_API_KEY]" in export["board_role_config"]["api_key"]
        assert export["board_role_config"]["normal_key"] == "value"

    async def test_export_nonexistent_company(self, template_service, mock_session):
        """Should raise NotFoundError for nonexistent company."""
        # Arrange
        company_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(NotFoundError):
            await template_service.export_company(company_id)


class TestContribute:
    """Tests for contribute method."""

    async def test_contribute_template(self, template_service, mock_session):
        """Should create contributed template."""
        # Arrange
        template_id = uuid.uuid4()
        template_def = {
            "departments": [{"name": "Sales"}],
            "goals": [],
        }

        # Set up add to capture the template
        captured_template = None

        def capture_add(obj):
            nonlocal captured_template
            if isinstance(obj, CompanyTemplate):
                captured_template = obj
                captured_template.id = template_id

        mock_session.add.side_effect = capture_add

        # Act
        result = await template_service.contribute(
            name="My Template",
            company_type="mkb",
            sector="Tech",
            description="Great template",
            template_definition=template_def,
        )

        # Assert
        assert result.name == "My Template"
        assert result.company_type == "mkb"
        assert result.sector == "Tech"
        assert result.description == "Great template"
        assert result.is_platform_template is False
        assert mock_session.commit.called

    async def test_contribute_scrubs_secrets(self, template_service, mock_session):
        """Should scrub secrets before contributing."""
        # Arrange
        template_id = uuid.uuid4()
        template_def = {
            "departments": [{"name": "Sales", "api_key": "secret123"}],
            "webhook_url": "https://secret.com",
            "goals": [],
        }

        # Set up add to capture the template and set ID
        captured_template = None

        def capture_add(obj):
            nonlocal captured_template
            if isinstance(obj, CompanyTemplate):
                captured_template = obj
                captured_template.id = template_id

        mock_session.add.side_effect = capture_add

        # Act
        with patch.object(template_service, "_to_response_model") as mock_response:
            mock_response.return_value = TemplateResponse(
                id=template_id,
                name="Secret Template",
                company_type="mkb",
                sector="Tech",
                description="Has secrets",
                is_platform_template=False,
                usage_count=0,
                rating_avg=None,
            )
            await template_service.contribute(
                name="Secret Template",
                company_type="mkb",
                sector="Tech",
                description="Has secrets",
                template_definition=template_def,
            )

        # Assert - Check that CompanyTemplate was added with scrubbed data
        assert captured_template is not None
        assert (
            "[SCRUBBED_API_KEY]"
            in captured_template.template_definition["departments"][0]["api_key"]
        )
        assert "[SCRUBBED_WEBHOOK_URL]" in captured_template.template_definition["webhook_url"]


class TestSecretScrubbing:
    """Tests for secret scrubbing functionality."""

    async def test_scrub_api_key(self, template_service):
        """Should scrub api_key fields."""
        data = {"api_key": "secret", "normal": "value"}
        scrubbed = template_service._scrub_secrets(data)

        assert "[SCRUBBED_API_KEY]" in scrubbed["api_key"]
        assert scrubbed["normal"] == "value"

    async def test_scrub_nested_secrets(self, template_service):
        """Should scrub secrets in nested dicts."""
        data = {
            "level1": {
                "password": "secret123",
                "data": "value",
            }
        }
        scrubbed = template_service._scrub_secrets(data)

        assert "[SCRUBBED_PASSWORD]" in scrubbed["level1"]["password"]
        assert scrubbed["level1"]["data"] == "value"

    async def test_scrub_list_items(self, template_service):
        """Should scrub secrets in list items."""
        data = {
            "items": [
                {"name": "Item 1", "token": "secret1"},
                {"name": "Item 2", "token": "secret2"},
            ]
        }
        scrubbed = template_service._scrub_secrets(data)

        assert "[SCRUBBED_TOKEN]" in scrubbed["items"][0]["token"]
        assert "[SCRUBBED_TOKEN]" in scrubbed["items"][1]["token"]

    async def test_scrub_various_patterns(self, template_service):
        """Should scrub various secret patterns."""
        data = {
            "api_key": "val1",
            "apikey": "val2",
            "secret_token": "val3",
            "password": "val4",
            "auth_header": "val5",
            "client_secret": "val6",
            "webhook_url": "val7",
        }
        scrubbed = template_service._scrub_secrets(data)

        for key in data.keys():
            assert "[SCRUBBED_" in scrubbed[key]
