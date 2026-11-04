"""
Tests for Canvas Templates.
"""

from datetime import datetime
from uuid import UUID, uuid4

import pytest

from src.domains.canvas.templates import (
    BLANK_TEMPLATE,
    PROJECT_KANBAN_TEMPLATE,
    CanvasTemplate,
    TemplateBlock,
    TemplateCategory,
    TemplateConnection,
    TemplateDifficulty,
    TemplateRegistry,
    template_registry,
)


class TestTemplateBlock:
    """Test TemplateBlock dataclass."""

    def test_block_creation(self):
        """Create a template block."""
        block = TemplateBlock(
            id="block1",
            type="text",
            x=100,
            y=200,
            width=300,
            height=150,
            content={"text": "Hello"},
        )

        assert block.id == "block1"
        assert block.type == "text"
        assert block.x == 100
        assert block.y == 200
        assert block.width == 300
        assert block.height == 150


class TestTemplateConnection:
    """Test TemplateConnection dataclass."""

    def test_connection_creation(self):
        """Create a template connection."""
        conn = TemplateConnection(
            source_block_id="block1",
            target_block_id="block2",
            connection_type="flow",
            label="next",
        )

        assert conn.source_block_id == "block1"
        assert conn.target_block_id == "block2"
        assert conn.connection_type == "flow"
        assert conn.label == "next"


class TestCanvasTemplate:
    """Test CanvasTemplate dataclass."""

    def test_template_creation(self):
        """Create a canvas template."""
        template = CanvasTemplate(
            id=uuid4(),
            name="Test Template",
            description="A test template",
            category=TemplateCategory.BUSINESS,
            difficulty=TemplateDifficulty.BEGINNER,
            blocks=[
                TemplateBlock(
                    id="b1",
                    type="text",
                    x=0,
                    y=0,
                    content={"text": "Hello"},
                ),
            ],
            tags=["test", "example"],
        )

        assert template.name == "Test Template"
        assert template.category == TemplateCategory.BUSINESS
        assert len(template.blocks) == 1
        assert "test" in template.tags

    def test_template_to_dict(self):
        """Convert template to dictionary."""
        template = CanvasTemplate(
            id=UUID("12345678-1234-1234-1234-123456789abc"),
            name="Test Template",
            description="Test description",
            category=TemplateCategory.DATA_ANALYSIS,
            difficulty=TemplateDifficulty.INTERMEDIATE,
            blocks=[
                TemplateBlock(
                    id="b1",
                    type="metric",
                    x=50,
                    y=50,
                    content={"value": 100},
                ),
            ],
            connections=[],
            tags=["data"],
            author="Test Author",
            version="1.0.0",
        )

        data = template.to_dict()

        assert data["name"] == "Test Template"
        assert data["category"] == "data_analysis"
        assert data["difficulty"] == "intermediate"
        assert len(data["blocks"]) == 1
        assert data["author"] == "Test Author"
        assert data["version"] == "1.0.0"


class TestTemplateRegistry:
    """Test TemplateRegistry."""

    def test_registry_initialization(self):
        """Registry loads with built-in templates."""
        registry = TemplateRegistry()

        # Should have built-in templates
        assert len(registry._templates) > 0

        # Should have blank template
        blank = registry.get(BLANK_TEMPLATE.id)
        assert blank is not None
        assert blank.name == "Blank Canvas"

    def test_register_template(self):
        """Register a new template."""
        registry = TemplateRegistry()

        template = CanvasTemplate(
            id=uuid4(),
            name="Custom Template",
            description="My custom template",
            category=TemplateCategory.CUSTOM,
            difficulty=TemplateDifficulty.BEGINNER,
            blocks=[],
            tags=["custom"],
        )

        registry.register(template)

        # Should be retrievable
        retrieved = registry.get(template.id)
        assert retrieved == template

    def test_unregister_template(self):
        """Unregister a template."""
        registry = TemplateRegistry()

        template = CanvasTemplate(
            id=uuid4(),
            name="Temp Template",
            description="Temporary",
            category=TemplateCategory.CUSTOM,
            difficulty=TemplateDifficulty.BEGINNER,
            blocks=[],
        )

        registry.register(template)
        assert registry.get(template.id) is not None

        registry.unregister(template.id)
        assert registry.get(template.id) is None

    def test_get_by_name(self):
        """Get template by name."""
        registry = TemplateRegistry()

        # Should find existing template
        template = registry.get_by_name("Blank Canvas")
        assert template is not None
        assert template.name == "Blank Canvas"

        # Should be case-insensitive
        template = registry.get_by_name("blank canvas")
        assert template is not None

        # Should return None for non-existent
        template = registry.get_by_name("Non Existent")
        assert template is None

    def test_list_templates(self):
        """List all templates."""
        registry = TemplateRegistry()

        templates = registry.list_templates()

        assert len(templates) > 0
        # Should be sorted by name
        names = [t.name for t in templates]
        assert names == sorted(names)

    def test_list_templates_by_category(self):
        """Filter templates by category."""
        registry = TemplateRegistry()

        templates = registry.list_templates(category=TemplateCategory.BLANK)

        assert len(templates) >= 1
        for t in templates:
            assert t.category == TemplateCategory.BLANK

    def test_list_templates_by_difficulty(self):
        """Filter templates by difficulty."""
        registry = TemplateRegistry()

        templates = registry.list_templates(difficulty=TemplateDifficulty.BEGINNER)

        assert len(templates) > 0
        for t in templates:
            assert t.difficulty == TemplateDifficulty.BEGINNER

    def test_list_templates_by_tags(self):
        """Filter templates by tags."""
        registry = TemplateRegistry()

        templates = registry.list_templates(tags=["kanban"])

        # Should include Project Kanban
        assert any(t.name == "Project Kanban Board" for t in templates)

    def test_list_templates_search(self):
        """Search templates by name/description."""
        registry = TemplateRegistry()

        templates = registry.list_templates(search="kanban")

        # Should find kanban template
        assert any("kanban" in t.name.lower() for t in templates)

    def test_get_categories(self):
        """Get all categories with counts."""
        registry = TemplateRegistry()

        categories = registry.get_categories()

        assert len(categories) > 0
        # Should have blank category
        blank_cat = next((c for c in categories if c["id"] == "blank"), None)
        assert blank_cat is not None
        assert blank_cat["count"] >= 1

    def test_get_tags(self):
        """Get all tags with counts."""
        registry = TemplateRegistry()

        tags = registry.get_tags()

        # Should have some tags from built-in templates
        assert len(tags) > 0

    def test_apply_template(self):
        """Apply template to create canvas content."""
        registry = TemplateRegistry()
        canvas_id = uuid4()

        result = registry.apply_template(
            template_id=PROJECT_KANBAN_TEMPLATE.id,
            canvas_id=canvas_id,
        )

        assert result["template_id"] == str(PROJECT_KANBAN_TEMPLATE.id)
        assert result["template_name"] == "Project Kanban Board"
        assert len(result["blocks"]) > 0
        assert "metadata" in result

        # Block IDs should be regenerated
        for block in result["blocks"]:
            assert "id" in block

    def test_apply_template_with_customizations(self):
        """Apply template with customizations."""
        registry = TemplateRegistry()
        canvas_id = uuid4()

        result = registry.apply_template(
            template_id=PROJECT_KANBAN_TEMPLATE.id,
            canvas_id=canvas_id,
            customizations={
                "todo_column": {"title": "📥 Backlog"},
            },
        )

        # Find the customized block
        todo_block = next(
            (b for b in result["blocks"] if b.get("content", {}).get("title") == "📥 Backlog"), None
        )
        assert todo_block is not None

    def test_apply_nonexistent_template(self):
        """Error when applying non-existent template."""
        registry = TemplateRegistry()

        with pytest.raises(ValueError, match="not found"):
            registry.apply_template(
                template_id=uuid4(),
                canvas_id=uuid4(),
            )


class TestBuiltInTemplates:
    """Test built-in template definitions."""

    def test_blank_template(self):
        """Blank template exists and is valid."""
        assert BLANK_TEMPLATE.name == "Blank Canvas"
        assert BLANK_TEMPLATE.category == TemplateCategory.BLANK
        assert len(BLANK_TEMPLATE.blocks) == 0

    def test_project_kanban_template(self):
        """Project Kanban template has expected structure."""
        assert PROJECT_KANBAN_TEMPLATE.name == "Project Kanban Board"
        assert PROJECT_KANBAN_TEMPLATE.category == TemplateCategory.PROJECT_MANAGEMENT

        # Should have kanban columns
        block_types = [b.type for b in PROJECT_KANBAN_TEMPLATE.blocks]
        assert "container" in block_types

    def test_data_dashboard_template(self):
        """Data Dashboard template exists."""
        from src.domains.canvas.templates import DATA_DASHBOARD_TEMPLATE

        assert DATA_DASHBOARD_TEMPLATE.name == "Data Analytics Dashboard"
        assert DATA_DASHBOARD_TEMPLATE.category == TemplateCategory.DATA_ANALYSIS

    def test_ai_workflow_template(self):
        """AI Workflow template exists."""
        from src.domains.canvas.templates import AI_WORKFLOW_TEMPLATE

        assert AI_WORKFLOW_TEMPLATE.name == "AI Agent Workflow"
        assert AI_WORKFLOW_TEMPLATE.category == TemplateCategory.AI_WORKFLOW
        assert len(AI_WORKFLOW_TEMPLATE.connections) > 0

    def test_meeting_notes_template(self):
        """Meeting Notes template exists."""
        from src.domains.canvas.templates import MEETING_NOTES_TEMPLATE

        assert MEETING_NOTES_TEMPLATE.name == "Meeting Notes"
        assert MEETING_NOTES_TEMPLATE.category == TemplateCategory.BUSINESS

    def test_sql_query_builder_template(self):
        """SQL Query Builder template exists."""
        from src.domains.canvas.templates import SQL_QUERY_BUILDER_TEMPLATE

        assert SQL_QUERY_BUILDER_TEMPLATE.name == "SQL Query Builder"
        assert SQL_QUERY_BUILDER_TEMPLATE.category == TemplateCategory.DATA_ANALYSIS


class TestGlobalRegistry:
    """Test global template registry instance."""

    def test_global_registry_exists(self):
        """Global registry is available."""
        assert template_registry is not None
        assert isinstance(template_registry, TemplateRegistry)

    def test_global_has_builtins(self):
        """Global registry has built-in templates."""
        assert len(template_registry._templates) >= 6  # At least 6 built-ins
