"""
Unit Tests for Template Registry
Tests for the template registry service and template instantiation functionality.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.services.template_registry import (
    TemplateRegistry,
    WorkflowTemplateData,
    get_template_registry,
)
from src.core.workflow.models import C7WorkflowTemplate as WorkflowTemplate


class TestTemplateRegistry:
    """Test suite for TemplateRegistry class."""

    @pytest.fixture
    def template_registry(self):
        """Create a fresh template registry for each test."""
        registry = TemplateRegistry()
        # Clear any existing templates
        registry._templates.clear()
        return registry

    @pytest.fixture
    def sample_template_data(self):
        """Sample template data for testing."""
        return WorkflowTemplateData(
            template_id="test_template_1",
            name="Test Template",
            category="testing",
            description="A test template",
            spec={
                "nodes": [
                    {
                        "id": "start",
                        "type": "trigger",
                        "config": {"type": "{{trigger_type}}"},
                    },
                    {
                        "id": "process",
                        "type": "task",
                        "config": {"message": "Hello {{name}}!"},
                    },
                ]
            },
            required_integrations=["test_integration"],
            author="test_author",
            is_public=True,
        )

    @pytest.fixture
    def sample_db_template(self):
        """Sample database template for testing."""
        return WorkflowTemplate(
            id=1,
            template_id="db_template_1",
            name="DB Template",
            category="database",
            description="Template from database",
            spec_json={
                "nodes": [
                    {
                        "id": "input",
                        "type": "data_source",
                        "config": {"source": "{{data_source}}"},
                    }
                ]
            },
            author="db_author",
            is_public=True,
            usage_count=0,
        )

    def test_singleton_pattern(self, template_registry):
        """Test that TemplateRegistry follows singleton pattern."""
        registry1 = TemplateRegistry()
        registry2 = TemplateRegistry()
        assert registry1 is registry2

    def test_get_template_registry_function(self):
        """Test that get_template_registry returns the singleton instance."""
        registry1 = get_template_registry()
        registry2 = get_template_registry()
        assert registry1 is registry2

    def test_add_and_get_template(self, template_registry, sample_template_data):
        """Test adding and retrieving a template."""
        # Add template
        template_registry._templates[sample_template_data.template_id] = sample_template_data

        # Retrieve template
        retrieved = template_registry.get_template(sample_template_data.template_id)
        assert retrieved is not None
        assert retrieved.template_id == sample_template_data.template_id
        assert retrieved.name == sample_template_data.name
        assert retrieved.category == sample_template_data.category
        assert retrieved.spec == sample_template_data.spec

    def test_get_nonexistent_template(self, template_registry):
        """Test retrieving a non-existent template."""
        template = template_registry.get_template("nonexistent")
        assert template is None

    def test_list_templates(self, template_registry, sample_template_data):
        """Test listing all templates."""
        # Add templates
        template_registry._templates[sample_template_data.template_id] = sample_template_data

        # Add another template with different category
        other_template = WorkflowTemplateData(
            template_id="other_template",
            name="Other Template",
            category="other",
            description="Another test template",
            spec={},
        )
        template_registry._templates[other_template.template_id] = other_template

        # List all templates
        all_templates = template_registry.list_templates()
        assert len(all_templates) == 2
        template_ids = {t.template_id for t in all_templates}
        assert sample_template_data.template_id in template_ids
        assert other_template.template_id in template_ids

    def test_list_templates_with_category_filter(self, template_registry, sample_template_data):
        """Test listing templates with category filter."""
        # Add templates
        template_registry._templates[sample_template_data.template_id] = sample_template_data

        # Add another template with different category
        other_template = WorkflowTemplateData(
            template_id="other_template",
            name="Other Template",
            category="other",
            description="Another test template",
            spec={},
        )
        template_registry._templates[other_template.template_id] = other_template

        # List templates with category filter
        filtered_templates = template_registry.list_templates(category="testing")
        assert len(filtered_templates) == 1
        assert filtered_templates[0].template_id == sample_template_data.template_id

    @pytest.mark.asyncio
    async def test_initialize_from_database(self, template_registry, sample_db_template):
        """Test initializing templates from database."""
        # Mock session and query result
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = [sample_db_template]
        mock_session.execute.return_value = mock_result

        # Initialize registry
        await template_registry.initialize(mock_session)

        # Verify template was loaded
        template = template_registry.get_template("db_template_1")
        assert template is not None
        assert template.template_id == "db_template_1"
        assert template.name == "DB Template"
        assert template.category == "database"

    def test_instantiate_template(self, template_registry, sample_template_data):
        """Test instantiating a template with parameters."""
        # Add template
        template_registry._templates[sample_template_data.template_id] = sample_template_data

        # Instantiate with parameters
        parameters = {"trigger_type": "webhook", "name": "World"}

        spec = template_registry.instantiate(sample_template_data.template_id, parameters)

        # Verify parameter substitution
        assert spec["nodes"][0]["config"]["type"] == "webhook"
        assert spec["nodes"][1]["config"]["message"] == "Hello World!"

    def test_instantiate_nonexistent_template(self, template_registry):
        """Test instantiating a non-existent template."""
        with pytest.raises(ValueError, match="Template 'nonexistent' not found"):
            template_registry.instantiate("nonexistent", {})

    def test_process_string_parameter_simple(self, template_registry):
        """Test processing simple string parameters."""
        parameters = {"name": "John", "age": 30}

        # Test direct parameter substitution
        result = template_registry._process_string_parameter("{{name}}", parameters)
        assert result == "John"

        result = template_registry._process_string_parameter("{{age}}", parameters)
        assert result == 30

    def test_process_string_parameter_embedded(self, template_registry):
        """Test processing embedded parameters in strings."""
        parameters = {"name": "John"}

        # Test embedded parameter substitution
        result = template_registry._process_string_parameter("Hello {{name}}!", parameters)
        assert result == "Hello John!"

    def test_process_string_parameter_nested(self, template_registry):
        """Test processing nested parameters."""
        parameters = {"user": {"name": "John", "profile": {"age": 30}}}

        # Test nested parameter access
        result = template_registry._process_string_parameter("{{user.name}}", parameters)
        assert result == "John"

        result = template_registry._process_string_parameter("{{user.profile.age}}", parameters)
        assert result == 30

    def test_substitute_parameters_in_dict(self, template_registry):
        """Test recursive parameter substitution in dictionaries."""
        obj = {
            "simple": "{{value1}}",
            "embedded": "Value is {{value2}}",
            "nested": {"inner": "{{value3}}"},
            "list": ["{{item1}}", "static", "{{item2}}"],
        }

        parameters = {
            "value1": "first",
            "value2": "second",
            "value3": "third",
            "item1": "list_item_1",
            "item2": "list_item_2",
        }

        template_registry._substitute_parameters(obj, parameters)

        assert obj["simple"] == "first"
        assert obj["embedded"] == "Value is second"
        assert obj["nested"]["inner"] == "third"
        assert obj["list"][0] == "list_item_1"
        assert obj["list"][1] == "static"
        assert obj["list"][2] == "list_item_2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
