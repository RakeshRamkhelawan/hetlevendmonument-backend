"""
Unit Tests for Template API Endpoints
Tests for the template API endpoints and request/response handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import User
from src.core.services.template_registry import TemplateRegistry, WorkflowTemplateData


class TestTemplateEndpoints:
    """Test suite for template API endpoints."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        user = MagicMock(spec=User)
        user.id = 1
        user.tenant_id = "test_tenant"
        user.username = "test_user"
        return user

    @pytest.fixture
    def mock_registry(self):
        """Create a mock template registry with async support."""
        registry = MagicMock(spec=TemplateRegistry)
        registry._templates = {}
        # CRITICAL: initialize() is async in TemplateRegistry
        registry.initialize = AsyncMock()
        return registry

    def test_list_templates_empty(self, client, mock_user):
        """Test listing templates when none exist."""
        with (
            patch("src.core.api.template_endpoints.get_template_registry") as mock_get_registry,
            patch("src.core.api.template_endpoints.get_db") as mock_get_db,
            patch("src.core.api.template_endpoints.get_current_user") as mock_get_user,
        ):
            # Setup mocks
            mock_get_user.return_value = mock_user
            mock_get_db.return_value = AsyncMock(spec=AsyncSession)
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()  # async method
            mock_registry.list_templates.return_value = []
            mock_get_registry.return_value = mock_registry

            # Make request
            response = client.get("/api/v1/workflow-templates/")

            # Verify response
            assert response.status_code == 200
            assert response.json() == []

    def test_list_templates_with_data(self, client, mock_user):
        """Test listing templates when templates exist."""
        with (
            patch("src.core.api.template_endpoints.get_template_registry") as mock_get_registry,
            patch("src.core.api.template_endpoints.get_db") as mock_get_db,
            patch("src.core.api.template_endpoints.get_current_user") as mock_get_user,
        ):
            # Setup mock templates
            mock_templates = [
                WorkflowTemplateData(
                    template_id="template_1",
                    name="Template 1",
                    category="category_1",
                    description="First template",
                    spec={"test": "data"},
                ),
                WorkflowTemplateData(
                    template_id="template_2",
                    name="Template 2",
                    category="category_2",
                    description="Second template",
                    spec={"test": "data2"},
                ),
            ]

            # Setup mocks
            mock_get_user.return_value = mock_user
            mock_get_db.return_value = AsyncMock(spec=AsyncSession)
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()  # async method
            mock_registry.list_templates.return_value = mock_templates
            mock_get_registry.return_value = mock_registry

            # Make request
            response = client.get("/api/v1/workflow-templates/")

            # Verify response
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["template_id"] == "template_1"
            assert data[1]["template_id"] == "template_2"

    def test_list_templates_with_category_filter(self, client, mock_user):
        """Test listing templates with category filter."""
        with (
            patch("src.core.api.template_endpoints.get_template_registry") as mock_get_registry,
            patch("src.core.api.template_endpoints.get_db") as mock_get_db,
            patch("src.core.api.template_endpoints.get_current_user") as mock_get_user,
        ):
            # Setup mock templates
            mock_templates = [
                WorkflowTemplateData(
                    template_id="template_1",
                    name="Template 1",
                    category="customer_service",
                    description="Customer service template",
                    spec={"test": "data"},
                )
            ]

            # Setup mocks
            mock_get_user.return_value = mock_user
            mock_get_db.return_value = AsyncMock(spec=AsyncSession)
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()  # async method
            mock_registry.list_templates.return_value = mock_templates
            mock_get_registry.return_value = mock_registry

            # Make request with category filter
            response = client.get("/api/v1/workflow-templates/?category=customer_service")

            # Verify response
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["category"] == "customer_service"

    def test_get_template_success(self, client, mock_user):
        """Test getting a specific template."""
        with (
            patch("src.core.api.template_endpoints.get_template_registry") as mock_get_registry,
            patch("src.core.api.template_endpoints.get_db") as mock_get_db,
            patch("src.core.api.template_endpoints.get_current_user") as mock_get_user,
        ):
            # Setup mock template
            mock_template = WorkflowTemplateData(
                template_id="test_template",
                name="Test Template",
                category="test",
                description="A test template",
                spec={"nodes": []},
            )

            # Setup mocks
            mock_get_user.return_value = mock_user
            mock_get_db.return_value = AsyncMock(spec=AsyncSession)
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()  # async method
            mock_registry.get_template.return_value = mock_template
            mock_get_registry.return_value = mock_registry

            # Make request
            response = client.get("/api/v1/workflow-templates/test_template")

            # Verify response
            assert response.status_code == 200
            data = response.json()
            assert data["template_id"] == "test_template"
            assert data["name"] == "Test Template"

    def test_get_template_not_found(self, client, mock_user):
        """Test getting a non-existent template."""
        with (
            patch("src.core.api.template_endpoints.get_template_registry") as mock_get_registry,
            patch("src.core.api.template_endpoints.get_db") as mock_get_db,
            patch("src.core.api.template_endpoints.get_current_user") as mock_get_user,
        ):
            # Setup mocks
            mock_get_user.return_value = mock_user
            mock_get_db.return_value = AsyncMock(spec=AsyncSession)
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()  # async method
            mock_registry.get_template.return_value = None
            mock_get_registry.return_value = mock_registry

            # Make request
            response = client.get("/api/v1/workflow-templates/nonexistent_template")

            # Verify response
            assert response.status_code == 404
            data = response.json()
            assert "error" in data
            assert data["error"]["error_code"] == "NOT_FOUND"

    def test_instantiate_template_success(self, client, mock_user):
        """Test instantiating a template successfully."""
        with (
            patch("src.core.api.template_endpoints.get_template_registry") as mock_get_registry,
            patch("src.core.api.template_endpoints.get_db") as mock_get_db,
            patch("src.core.api.template_endpoints.get_current_user") as mock_get_user,
        ):
            # Setup mock instantiated spec
            mock_spec = {"nodes": [{"id": "start", "type": "trigger"}]}

            # Setup mocks
            mock_get_user.return_value = mock_user
            mock_get_db.return_value = AsyncMock(spec=AsyncSession)
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()  # async method
            mock_registry.instantiate.return_value = mock_spec
            mock_get_registry.return_value = mock_registry

            # Make request
            request_data = {
                "workflow_name": "My Workflow",
                "parameters": {"param1": "value1"},
            }
            response = client.post(
                "/api/v1/workflow-templates/test_template/instantiate",
                json=request_data,
            )

            # Verify response
            assert response.status_code == 200
            data = response.json()
            assert data["workflow_name"] == "My Workflow"
            assert data["template_id"] == "test_template"
            assert data["spec"] == mock_spec

    def test_instantiate_template_not_found(self, client, mock_user):
        """Test instantiating a non-existent template."""
        with (
            patch("src.core.api.template_endpoints.get_template_registry") as mock_get_registry,
            patch("src.core.api.template_endpoints.get_db") as mock_get_db,
            patch("src.core.api.template_endpoints.get_current_user") as mock_get_user,
        ):
            # Setup mocks to raise ValueError for non-existent template
            mock_get_user.return_value = mock_user
            mock_get_db.return_value = AsyncMock(spec=AsyncSession)
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()  # async method
            mock_registry.instantiate.side_effect = ValueError("Template 'nonexistent' not found")
            mock_get_registry.return_value = mock_registry

            # Make request
            request_data = {"workflow_name": "My Workflow", "parameters": {}}
            response = client.post(
                "/api/v1/workflow-templates/nonexistent/instantiate", json=request_data
            )

            # Verify response
            assert response.status_code == 404
            data = response.json()
            assert "error" in data
            assert data["error"]["error_code"] == "NOT_FOUND"

    def test_search_templates(self, client, mock_user):
        """Test searching templates by query."""
        with (
            patch("src.core.api.template_endpoints.get_template_registry") as mock_get_registry,
            patch("src.core.api.template_endpoints.get_db") as mock_get_db,
            patch("src.core.api.template_endpoints.get_current_user") as mock_get_user,
        ):
            # Setup mock templates
            mock_templates = [
                WorkflowTemplateData(
                    template_id="ticket_triage",
                    name="Customer Ticket Triage",
                    category="customer_service",
                    description="Classify and route support tickets",
                    spec={},
                ),
                WorkflowTemplateData(
                    template_id="feedback_analysis",
                    name="Customer Feedback Analysis",
                    category="customer_service",
                    description="Analyze customer feedback sentiment",
                    spec={},
                ),
            ]

            # Setup mocks
            mock_get_user.return_value = mock_user
            mock_get_db.return_value = AsyncMock(spec=AsyncSession)
            mock_registry = MagicMock()
            mock_registry.initialize = AsyncMock()  # async method
            mock_registry.list_templates.return_value = mock_templates
            mock_get_registry.return_value = mock_registry

            # Make request to search for "customer"
            response = client.get("/api/v1/workflow-templates/search/?q=customer")

            # Verify response
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            # Both templates should match as they're in customer_service category
            # and have "customer" in their name or description


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
