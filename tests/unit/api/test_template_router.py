"""Unit tests for Template API Router.

Tests all template endpoints with mocked services.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from httpx import AsyncClient

from src.core.company.schemas import (
    CompanyResponse,
    TemplateContributeRequest,
    TemplateInstantiateRequest,
    TemplateListResponse,
    TemplateResponse,
)


# Create a simple test app
@pytest.fixture
def app(mock_template_service):
    """Create FastAPI app with template router."""
    from fastapi import APIRouter, Depends

    app = FastAPI()

    # Mock current user
    async def mock_require_authenticated_user():
        return {"user_id": 1, "tenant_id": 1}

    # Mock template service dependency
    def mock_get_template_service():
        return mock_template_service

    # Import and setup router with mocked deps
    from src.core.api.v1.company import template_router

    # Override dependencies
    template_router.router.dependencies = []

    app.include_router(template_router.router)

    # Override deps after including router
    app.dependency_overrides[template_router.require_authenticated_user] = (
        mock_require_authenticated_user
    )
    app.dependency_overrides[template_router.get_template_service] = mock_get_template_service

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


class TestListTemplates:
    """Tests for GET /templates endpoint."""

    def test_list_templates_success(self, client, mock_template_service):
        """Should return list of templates."""
        # Arrange
        templates = [
            TemplateResponse(
                id=uuid.uuid4(),
                name="Tech Startup",
                company_type="mkb",
                sector="Technologie",
                description="Ideal for startups",
                is_platform_template=True,
                usage_count=100,
                rating_avg=4.5,
            ),
            TemplateResponse(
                id=uuid.uuid4(),
                name="Freelancer",
                company_type="zzp",
                sector="Consultancy",
                description="For freelancers",
                is_platform_template=True,
                usage_count=50,
                rating_avg=4.2,
            ),
        ]
        mock_template_service.list_templates = AsyncMock(return_value=templates)

        # Act
        response = client.get("/templates")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 2
        assert len(data["templates"]) == 2

    def test_list_templates_empty(self, client, mock_template_service):
        """Should return empty list when no templates."""
        # Arrange
        mock_template_service.list_templates = AsyncMock(return_value=[])

        # Act
        response = client.get("/templates")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["total"] == 0
        assert response.json()["templates"] == []


class TestGetTemplate:
    """Tests for GET /templates/{id} endpoint."""

    def test_get_template_success(self, client, mock_template_service):
        """Should return template details."""
        # Arrange
        template_id = uuid.uuid4()
        template = TemplateResponse(
            id=template_id,
            name="Tech Startup",
            company_type="mkb",
            sector="Technologie",
            description="Ideal for startups",
            is_platform_template=True,
            usage_count=100,
            rating_avg=4.5,
        )
        mock_template_service.get_template = AsyncMock(return_value=template)

        # Act
        response = client.get(f"/templates/{template_id}")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(template_id)
        assert data["name"] == "Tech Startup"

    def test_get_template_not_found(self, client, mock_template_service):
        """Should return 404 for nonexistent template."""
        # Arrange
        from src.core.exceptions.exceptions import NotFoundError

        mock_template_service.get_template = AsyncMock(
            side_effect=NotFoundError("Template not found")
        )

        # Act
        response = client.get(f"/templates/{uuid.uuid4()}")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestInstantiateTemplate:
    """Tests for POST /templates/{id}/instantiate endpoint."""

    def test_instantiate_success(self, client, mock_template_service):
        """Should create company from template."""
        # Arrange
        template_id = uuid.uuid4()
        company_id = uuid.uuid4()
        company = CompanyResponse(
            id=company_id,
            tenant_id=1,
            name="My Startup",
            company_type="mkb",
            sector="Technologie",
            mission=None,
            status="active",
            departments_count=3,
            goals_count=2,
            created_at=datetime.now(timezone.utc),
        )
        mock_template_service.instantiate = AsyncMock(return_value=company)

        request_data = {
            "template_id": str(template_id),
            "company_name": "My Startup",
        }

        # Act
        response = client.post(f"/templates/{template_id}/instantiate", json=request_data)

        # Assert
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "My Startup"
        assert data["company_type"] == "mkb"

    def test_instantiate_template_not_found(self, client, mock_template_service):
        """Should return 404 for nonexistent template."""
        # Arrange
        from src.core.exceptions.exceptions import NotFoundError

        mock_template_service.instantiate = AsyncMock(
            side_effect=NotFoundError("Template not found")
        )

        request_data = {
            "template_id": str(uuid.uuid4()),
            "company_name": "My Startup",
        }

        # Act
        response = client.post(f"/templates/{uuid.uuid4()}/instantiate", json=request_data)

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestExportCompany:
    """Tests for POST /templates/export/{id} endpoint."""

    def test_export_success(self, client, mock_template_service):
        """Should export company as template definition."""
        # Arrange
        company_id = uuid.uuid4()
        export_data = {
            "name": "Test Company Template",
            "company_type": "mkb",
            "sector": "Technologie",
            "departments": [{"name": "Sales"}],
            "goals": [],
        }
        mock_template_service.export_company = AsyncMock(return_value=export_data)

        # Act
        response = client.post(f"/templates/export/{company_id}")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Test Company Template"

    def test_export_company_not_found(self, client, mock_template_service):
        """Should return 404 for nonexistent company."""
        # Arrange
        from src.core.exceptions.exceptions import NotFoundError

        mock_template_service.export_company = AsyncMock(
            side_effect=NotFoundError("Company not found")
        )

        # Act
        response = client.post(f"/templates/export/{uuid.uuid4()}")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestContributeTemplate:
    """Tests for POST /templates/contribute endpoint."""

    def test_contribute_success(self, client, mock_template_service):
        """Should create contributed template."""
        # Arrange
        template_id = uuid.uuid4()
        template = TemplateResponse(
            id=template_id,
            name="My Custom Template",
            company_type="mkb",
            sector="Technologie",
            description="Custom template",
            is_platform_template=False,
            usage_count=0,
            rating_avg=None,
        )
        mock_template_service.contribute = AsyncMock(return_value=template)

        request_data = {
            "name": "My Custom Template",
            "company_type": "mkb",
            "sector": "Technologie",
            "description": "Custom template",
            "template_definition": {
                "departments": [{"name": "Sales"}],
                "goals": [],
            },
        }

        # Act
        response = client.post("/templates/contribute", json=request_data)

        # Assert
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "My Custom Template"
        assert data["is_platform_template"] is False


class TestListTypesAndSectors:
    """Tests for utility endpoints."""

    def test_list_company_types(self, client):
        """Should return list of company types."""
        # Act
        response = client.get("/templates/types/list")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "mkb" in data
        assert "zzp" in data
        assert "enterprise" in data

    def test_list_sectors(self, client):
        """Should return list of sectors."""
        # Act
        response = client.get("/templates/sectors/list")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "Technologie" in data
        assert "Horeca" in data
        assert "Retail" in data
