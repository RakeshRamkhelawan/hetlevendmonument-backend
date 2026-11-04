"""Unit tests for Onboarding API Router.

Tests the 3-step onboarding wizard:
- Step 1: Get recommended templates
- Step 2: AI template matching
- Step 3: Complete onboarding
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.company.schemas import (
    CompanyResponse,
    OnboardingAIMatchRequest,
    OnboardingAIMatchResponse,
    OnboardingCompleteRequest,
    TemplateListResponse,
    TemplateResponse,
)


# Create a simple test app
@pytest.fixture
def app(mock_template_service):
    """Create FastAPI app with onboarding router."""
    from fastapi import APIRouter, Depends

    app = FastAPI()

    # Mock current user
    async def mock_require_authenticated_user():
        return {"user_id": 1, "tenant_id": 1}

    # Mock template service dependency
    def mock_get_template_service():
        return mock_template_service

    # Import and setup router with mocked deps
    from src.core.api.v1.company import onboarding_router

    # Override dependencies
    onboarding_router.router.dependencies = []

    app.include_router(onboarding_router.router)

    # Override deps after including router
    app.dependency_overrides[onboarding_router.require_authenticated_user] = (
        mock_require_authenticated_user
    )
    app.dependency_overrides[onboarding_router.get_template_service] = mock_get_template_service

    # OP-175: `router.dependencies = []` above does not retroactively strip the
    # router-level `Depends(require_company_layer_enabled)` baked into each route
    # at import time, so requests reached the real Redis client. Override it
    # explicitly (same pattern as tests/unit/test_goal.py).
    from src.core.api.v1.company.feature_flags_dependency import require_company_layer_enabled

    app.dependency_overrides[require_company_layer_enabled] = lambda: None

    return app


@pytest.fixture
def mock_template_service():
    """Create a mock template service."""
    return MagicMock()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestGetRecommendedTemplates:
    """Tests for GET /onboarding/templates endpoint."""

    def test_get_templates_by_company_type(self, client, mock_template_service):
        """Should return templates filtered by company type."""
        # Arrange
        templates = [
            TemplateResponse(
                id=uuid.uuid4(),
                name="Tech Startup MKB",
                company_type="mkb",
                sector="Technologie",
                description="Ideal for startups",
                is_platform_template=True,
                usage_count=100,
                rating_avg=4.5,
            ),
            TemplateResponse(
                id=uuid.uuid4(),
                name="Horeca MKB",
                company_type="mkb",
                sector="Horeca",
                description="For restaurants",
                is_platform_template=True,
                usage_count=50,
                rating_avg=4.2,
            ),
        ]
        mock_template_service.list_templates = AsyncMock(return_value=templates)

        # Act
        response = client.get("/onboarding/templates?company_type=mkb")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["templates"]) == 2

    def test_get_templates_with_sector_filter(self, client, mock_template_service):
        """Should filter templates by sector."""
        # Arrange
        templates = [
            TemplateResponse(
                id=uuid.uuid4(),
                name="Tech Startup MKB",
                company_type="mkb",
                sector="Technologie",
                description="Ideal for startups",
                is_platform_template=True,
                usage_count=100,
                rating_avg=4.5,
            ),
        ]
        mock_template_service.list_templates = AsyncMock(return_value=templates)

        # Act
        response = client.get("/onboarding/templates?company_type=mkb&sector=Technologie")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["templates"]) == 1

    def test_get_templates_empty_result(self, client, mock_template_service):
        """Should return empty list when no templates match."""
        # Arrange
        mock_template_service.list_templates = AsyncMock(return_value=[])

        # Act
        response = client.get("/onboarding/templates?company_type=unknown")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["templates"] == []

    def test_get_templates_limited_to_top_3(self, client, mock_template_service):
        """Should return max 3 templates."""
        # Arrange
        templates = [
            TemplateResponse(
                id=uuid.uuid4(),
                name=f"Template {i}",
                company_type="mkb",
                sector="Tech",
                description=f"Template {i}",
                is_platform_template=True,
                usage_count=100 - i,
                rating_avg=4.0,
            )
            for i in range(5)
        ]
        mock_template_service.list_templates = AsyncMock(return_value=templates)

        # Act
        response = client.get("/onboarding/templates?company_type=mkb")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3  # Limited to top 3
        assert len(data["templates"]) == 3


class TestAIMatchTemplate:
    """Tests for POST /onboarding/ai-match endpoint."""

    def test_ai_match_tech_startup(self, client, mock_template_service):
        """Should match tech-related description to tech startup template."""
        # Arrange
        template_id = uuid.uuid4()
        template = TemplateResponse(
            id=template_id,
            name="Tech Startup MKB",
            company_type="mkb",
            sector="Technologie",
            description="Ideal for tech startups",
            is_platform_template=True,
            usage_count=100,
            rating_avg=4.5,
        )
        mock_template_service.list_templates = AsyncMock(return_value=[template])

        request_data = {"description": "Ik wil een software startup met AI en machine learning"}

        # Act
        response = client.post("/onboarding/ai-match", json=request_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["template_name"] == "Tech Startup MKB"
        assert data["confidence"] > 0.5
        assert "tech" in data["match_reason"].lower() or "ai" in data["match_reason"].lower()

    def test_ai_match_retail(self, client, mock_template_service):
        """Should match retail-related description to retail template."""
        # Arrange
        template_id = uuid.uuid4()
        template = TemplateResponse(
            id=template_id,
            name="Retail Winkel MKB",
            company_type="mkb",
            sector="Retail",
            description="For retail stores",
            is_platform_template=True,
            usage_count=80,
            rating_avg=4.3,
        )
        mock_template_service.list_templates = AsyncMock(return_value=[template])

        request_data = {"description": "Ik wil een online winkel met webshop voor producten"}

        # Act
        response = client.post("/onboarding/ai-match", json=request_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert (
            "retail" in data["template_name"].lower() or "winkel" in data["template_name"].lower()
        )

    def test_ai_match_horeca(self, client, mock_template_service):
        """Should match hospitality description to horeca template."""
        # Arrange
        template_id = uuid.uuid4()
        template = TemplateResponse(
            id=template_id,
            name="Horeca MKB",
            company_type="mkb",
            sector="Horeca",
            description="For restaurants",
            is_platform_template=True,
            usage_count=60,
            rating_avg=4.0,
        )
        mock_template_service.list_templates = AsyncMock(return_value=[template])

        request_data = {"description": "Ik wil een restaurant openen met keuken en bediening"}

        # Act
        response = client.post("/onboarding/ai-match", json=request_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert (
            "horeca" in data["template_name"].lower()
            or "restaurant" in data["template_name"].lower()
        )

    def test_ai_match_no_specific_match(self, client, mock_template_service):
        """Should return default template with low confidence for unknown description."""
        # Arrange
        template_id = uuid.uuid4()
        template = TemplateResponse(
            id=template_id,
            name="Tech Startup MKB",
            company_type="mkb",
            sector="Technologie",
            description="Default",
            is_platform_template=True,
            usage_count=100,
            rating_avg=4.5,
        )
        mock_template_service.list_templates = AsyncMock(return_value=[template])

        request_data = {"description": "xyz abc unknown business type completely different"}

        # Act
        response = client.post("/onboarding/ai-match", json=request_data)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["confidence"] < 0.5  # Low confidence

    def test_ai_match_validation_error(self, client):
        """Should return 422 for invalid request."""
        # Arrange
        request_data = {"description": "short"}  # Too short (min 10 chars)

        # Act
        response = client.post("/onboarding/ai-match", json=request_data)

        # Assert
        assert response.status_code == 422

    def test_ai_match_no_templates_available(self, client, mock_template_service):
        """Should return 404 when no templates available."""
        # Arrange
        mock_template_service.list_templates = AsyncMock(return_value=[])

        request_data = {"description": "Tech startup met software ontwikkeling"}

        # Act
        response = client.post("/onboarding/ai-match", json=request_data)

        # Assert
        assert response.status_code == 404


class TestCompleteOnboarding:
    """Tests for POST /onboarding/complete endpoint."""

    def test_complete_with_template(self, client, mock_template_service):
        """Should create company using template."""
        # Arrange
        template_id = uuid.uuid4()
        company_id = uuid.uuid4()
        company = CompanyResponse(
            id=company_id,
            tenant_id=1,
            name="My Startup",
            company_type="mkb",
            sector="Technologie",
            mission="Onze missie",
            status="active",
            departments_count=3,
            goals_count=2,
            created_at=datetime.now(timezone.utc),
        )
        mock_template_service.instantiate = AsyncMock(return_value=company)

        request_data = {
            "template_id": str(template_id),
            "company_name": "My Startup",
            "company_type": "mkb",
            "sector": "Technologie",
            "mission": "Onze missie",
        }

        # Act
        response = client.post("/onboarding/complete", json=request_data)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Startup"
        assert data["company_type"] == "mkb"

    def test_complete_without_template(self, client):
        """Should return 422 when no template provided."""
        # Arrange
        request_data = {
            "company_name": "My Company",
            "company_type": "mkb",
            "sector": "Technologie",
        }

        # Act
        response = client.post("/onboarding/complete", json=request_data)

        # Assert
        assert response.status_code == 422

    def test_complete_template_not_found(self, client, mock_template_service):
        """Should return 404 when template not found."""
        # Arrange
        from src.core.exceptions.exceptions import NotFoundError

        mock_template_service.instantiate = AsyncMock(
            side_effect=NotFoundError("Template not found")
        )

        request_data = {
            "template_id": str(uuid.uuid4()),
            "company_name": "My Startup",
            "company_type": "mkb",
            "sector": "Technologie",
        }

        # Act
        response = client.post("/onboarding/complete", json=request_data)

        # Assert
        assert response.status_code == 404

    def test_complete_validation_error(self, client):
        """Should return 422 for invalid company data."""
        # Arrange
        request_data = {
            "template_id": str(uuid.uuid4()),
            "company_name": "A",  # Too short (min 2)
            "company_type": "mkb",
            "sector": "Technologie",
        }

        # Act
        response = client.post("/onboarding/complete", json=request_data)

        # Assert
        assert response.status_code == 422


class TestGetOnboardingStatus:
    """Tests for GET /onboarding/status endpoint."""

    def test_status_not_completed(self, client):
        """Should return not completed status for new user."""
        # Act
        response = client.get("/onboarding/status")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["completed"] is False
        assert data["company_id"] is None
        assert data["next_step"] == "template_selection"
