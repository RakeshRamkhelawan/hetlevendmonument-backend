"""Unit tests for Onboarding API Router (Fase 7.2).

Tests all endpoints in onboarding_router.py:
- GET  /onboarding/templates   -> get_recommended_templates
- POST /onboarding/ai-match    -> ai_match_template
- POST /onboarding/complete    -> complete_onboarding
- GET  /onboarding/status      -> get_onboarding_status

Also tests internal helper _match_description_to_template.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.api.v1.company.onboarding_router import (
    _match_description_to_template,
    ai_match_template,
    complete_onboarding,
    get_onboarding_status,
    get_recommended_templates,
)
from src.core.company.schemas import (
    CompanyResponse,
    OnboardingAIMatchRequest,
    OnboardingCompleteRequest,
    TemplateListResponse,
    TemplateResponse,
)
from src.core.company.template_service import TemplateService
from src.core.exceptions.exceptions import NotFoundError

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_template_service():
    """Create mock TemplateService with all async methods."""
    service = MagicMock(spec=TemplateService)
    service.list_templates = AsyncMock()
    service.instantiate = AsyncMock()
    return service


@pytest.fixture
def sample_template():
    """Create a sample TemplateResponse."""
    return TemplateResponse(
        id=uuid.uuid4(),
        name="Tech Startup MKB",
        company_type="mkb",
        sector="Tech",
        description="Een technologie startup template",
        is_platform_template=True,
        usage_count=25,
        rating_avg=4.5,
    )


@pytest.fixture
def mock_authenticated_user():
    """Create mock authenticated user dict."""
    return {
        "user_id": 1,
        "tenant_id": 1,
        "email": "test@example.com",
        "company_id": None,
    }


# ============================================================================
# Happy Path Tests - Keyword Matching
# ============================================================================


class TestKeywordMatching:
    """Test _match_description_to_template helper."""

    def test_match_tech_startup(self):
        """Tech-beschrijving -> tech_startup match."""
        key, confidence, reason = _match_description_to_template("Ik bouw een AI software platform")
        assert key == "tech_startup"
        assert confidence > 0.1

    def test_match_freelance_consultant(self):
        """Consultant-beschrijving -> freelance_consultant match."""
        key, confidence, reason = _match_description_to_template(
            "Ik werk als zelfstandige consultant voor projecten"
        )
        assert key == "freelance_consultant"
        assert confidence > 0.1

    def test_match_horeca(self):
        """Restaurant-beschrijving -> horeca match."""
        key, confidence, reason = _match_description_to_template(
            "Ik heb een restaurant en cafe in de binnenstad"
        )
        assert key == "horeca"
        assert confidence > 0.1

    def test_no_match_default(self):
        """Vage beschrijving -> tech_startup default met lage confidence."""
        key, confidence, reason = _match_description_to_template("Ik doe wat dingen hier en daar")
        assert key == "tech_startup"
        assert confidence == 0.3
        assert "default" in reason.lower() or "geen" in reason.lower()


# ============================================================================
# Happy Path Tests - Endpoints
# ============================================================================


class TestGetRecommendedTemplates:
    """Test GET /onboarding/templates endpoint."""

    @pytest.mark.asyncio
    async def test_get_recommended_templates_success(
        self, mock_template_service, sample_template, mock_authenticated_user
    ):
        """GET templates met company_type -> top 3 templates."""
        mock_template_service.list_templates.return_value = [
            sample_template,
            sample_template,
            sample_template,
        ]

        result = await get_recommended_templates(
            company_type="mkb",
            sector=None,
            template_service=mock_template_service,
            _authenticated=mock_authenticated_user,
        )

        assert isinstance(result, TemplateListResponse)
        assert result.total <= 3
        mock_template_service.list_templates.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_recommended_templates_with_sector(
        self, mock_template_service, sample_template, mock_authenticated_user
    ):
        """GET templates met sector filter -> gefilterde lijst."""
        mock_template_service.list_templates.return_value = [sample_template]

        result = await get_recommended_templates(
            company_type="mkb",
            sector="Tech",
            template_service=mock_template_service,
            _authenticated=mock_authenticated_user,
        )

        assert result.total == 1
        call_args = mock_template_service.list_templates.call_args
        assert call_args[0][0]["sector"] == "Tech"

    @pytest.mark.asyncio
    async def test_get_recommended_templates_empty(
        self, mock_template_service, mock_authenticated_user
    ):
        """GET templates zonder resultaten -> lege lijst."""
        mock_template_service.list_templates.return_value = []

        result = await get_recommended_templates(
            company_type="enterprise",
            sector=None,
            template_service=mock_template_service,
            _authenticated=mock_authenticated_user,
        )

        assert result.total == 0
        assert result.templates == []


class TestAIMatchTemplate:
    """Test POST /onboarding/ai-match endpoint."""

    @pytest.mark.asyncio
    async def test_ai_match_success(
        self, mock_template_service, sample_template, mock_authenticated_user
    ):
        """POST ai-match met tech beschrijving -> match met confidence."""
        # Template name must match the TEMPLATE_NAME_MAP
        sample_template.name = "Tech Startup MKB"
        mock_template_service.list_templates.return_value = [sample_template]

        data = OnboardingAIMatchRequest(
            description="Ik bouw een AI software platform voor tech bedrijven"
        )

        result = await ai_match_template(
            data=data,
            template_service=mock_template_service,
            _authenticated=mock_authenticated_user,
        )

        assert result.template_name == "Tech Startup MKB"
        assert result.confidence > 0.0
        assert result.template_id == sample_template.id

    @pytest.mark.asyncio
    async def test_ai_match_no_templates_404(self, mock_template_service, mock_authenticated_user):
        """POST ai-match zonder templates -> 404."""
        mock_template_service.list_templates.return_value = []

        data = OnboardingAIMatchRequest(description="Ik heb een bedrijf")

        with pytest.raises(HTTPException) as exc_info:
            await ai_match_template(
                data=data,
                template_service=mock_template_service,
                _authenticated=mock_authenticated_user,
            )

        assert exc_info.value.status_code == 404


class TestCompleteOnboarding:
    """Test POST /onboarding/complete endpoint."""

    @pytest.mark.asyncio
    async def test_complete_with_template(self, mock_template_service, mock_authenticated_user):
        """POST complete met template_id -> CompanyResponse."""
        template_id = uuid.uuid4()
        company_response = CompanyResponse(
            id=uuid.uuid4(),
            tenant_id=1,
            name="My Company",
            company_type="mkb",
            sector="Tech",
            mission="Build great software",
            status="active",
            departments_count=3,
            goals_count=1,
            created_at=datetime.now(timezone.utc),
        )
        mock_template_service.instantiate.return_value = company_response

        data = OnboardingCompleteRequest(
            template_id=template_id,
            company_name="My Company",
            company_type="mkb",
            sector="Tech",
        )

        result = await complete_onboarding(
            data=data,
            template_service=mock_template_service,
            _authenticated=mock_authenticated_user,
        )

        assert result.name == "My Company"
        assert result.status == "active"
        mock_template_service.instantiate.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_without_template_422(
        self, mock_template_service, mock_authenticated_user
    ):
        """POST complete zonder template_id -> 422."""
        data = OnboardingCompleteRequest(
            company_name="My Company",
            company_type="mkb",
            sector="Tech",
        )

        with pytest.raises(HTTPException) as exc_info:
            await complete_onboarding(
                data=data,
                template_service=mock_template_service,
                _authenticated=mock_authenticated_user,
            )

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_complete_template_not_found_404(
        self, mock_template_service, mock_authenticated_user
    ):
        """POST complete met onbekend template_id -> 404."""
        mock_template_service.instantiate.side_effect = NotFoundError("Template not found")

        data = OnboardingCompleteRequest(
            template_id=uuid.uuid4(),
            company_name="My Company",
            company_type="mkb",
            sector="Tech",
        )

        with pytest.raises(HTTPException) as exc_info:
            await complete_onboarding(
                data=data,
                template_service=mock_template_service,
                _authenticated=mock_authenticated_user,
            )

        assert exc_info.value.status_code == 404


class TestGetOnboardingStatus:
    """Test GET /onboarding/status endpoint."""

    @pytest.mark.asyncio
    async def test_status_not_completed(self):
        """User zonder company_id -> completed=False."""
        user = {"user_id": 1, "tenant_id": 1, "company_id": None}

        result = await get_onboarding_status(current_user=user)

        assert result["completed"] is False
        assert result["next_step"] == "template_selection"

    @pytest.mark.asyncio
    async def test_status_completed(self):
        """User met company_id -> completed=True."""
        company_id = str(uuid.uuid4())
        user = {"user_id": 1, "tenant_id": 1, "company_id": company_id}

        result = await get_onboarding_status(current_user=user)

        assert result["completed"] is True
        assert result["company_id"] == company_id
        assert result["next_step"] is None
