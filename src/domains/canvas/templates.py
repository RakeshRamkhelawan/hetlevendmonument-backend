"""
Canvas Templates System

Provides pre-built canvas layouts and templates for quick starts.
Supports custom templates, categories, and template inheritance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from loguru import logger
from pydantic import BaseModel, Field


class TemplateCategory(str, Enum):
    """Categories for canvas templates."""

    BLANK = "blank"
    BUSINESS = "business"
    DATA_ANALYSIS = "data_analysis"
    PROJECT_MANAGEMENT = "project_management"
    WORKFLOW = "workflow"
    DASHBOARD = "dashboard"
    AI_WORKFLOW = "ai_workflow"
    CUSTOM = "custom"


class TemplateDifficulty(str, Enum):
    """Difficulty level for templates."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


@dataclass
class TemplateBlock:
    """A block definition within a template."""

    id: str
    type: str
    x: float
    y: float
    width: float = 200
    height: float = 100
    content: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    style: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    connections: list[str] = field(default_factory=list)


@dataclass
class TemplateConnection:
    """A connection definition within a template."""

    source_block_id: str
    target_block_id: str
    connection_type: str = "default"
    label: str | None = None
    style: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


@dataclass
class CanvasTemplate:
    """A canvas template definition."""

    id: UUID
    name: str
    description: str
    category: TemplateCategory
    difficulty: TemplateDifficulty
    blocks: list[TemplateBlock]
    connections: list[TemplateConnection] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    author: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "1.0.0"
    preview_image: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert template to dictionary."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "difficulty": self.difficulty.value,
            "blocks": [
                {
                    "id": b.id,
                    "type": b.type,
                    "x": b.x,
                    "y": b.y,
                    "width": b.width,
                    "height": b.height,
                    "content": b.content,
                    "style": b.style,
                    "connections": b.connections,
                }
                for b in self.blocks
            ],
            "connections": [
                {
                    "source": c.source_block_id,
                    "target": c.target_block_id,
                    "type": c.connection_type,
                    "label": c.label,
                    "style": c.style,
                }
                for c in self.connections
            ],
            "tags": self.tags,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
            "preview_image": self.preview_image,
            "metadata": self.metadata,
        }


# ============================================================================
# Built-in Templates
# ============================================================================

BLANK_TEMPLATE = CanvasTemplate(
    id=UUID("00000000-0000-0000-0000-000000000001"),
    name="Blank Canvas",
    description="Start with a clean slate",
    category=TemplateCategory.BLANK,
    difficulty=TemplateDifficulty.BEGINNER,
    blocks=[],
    tags=["empty", "minimal"],
)

PROJECT_KANBAN_TEMPLATE = CanvasTemplate(
    id=UUID("00000000-0000-0000-0000-000000000002"),
    name="Project Kanban Board",
    description="Track tasks through stages: To Do, In Progress, Done",
    category=TemplateCategory.PROJECT_MANAGEMENT,
    difficulty=TemplateDifficulty.BEGINNER,
    blocks=[
        TemplateBlock(
            id="todo_column",
            type="container",
            x=50,
            y=50,
            width=250,
            height=600,
            content={"title": "[LIST] To Do", "color": "#f0f0f0"},
        ),
        TemplateBlock(
            id="inprogress_column",
            type="container",
            x=350,
            y=50,
            width=250,
            height=600,
            content={"title": "[U+0001F504] In Progress", "color": "#fff3cd"},
        ),
        TemplateBlock(
            id="done_column",
            type="container",
            x=650,
            y=50,
            width=250,
            height=600,
            content={"title": "[OK] Done", "color": "#d4edda"},
        ),
        TemplateBlock(
            id="task1",
            type="task",
            x=70,
            y=100,
            width=210,
            height=80,
            content={"title": "Sample Task", "status": "todo"},
        ),
    ],
    tags=["kanban", "agile", "project"],
)

DATA_DASHBOARD_TEMPLATE = CanvasTemplate(
    id=UUID("00000000-0000-0000-0000-000000000003"),
    name="Data Analytics Dashboard",
    description="Monitor KPIs with charts and metrics",
    category=TemplateCategory.DATA_ANALYSIS,
    difficulty=TemplateDifficulty.INTERMEDIATE,
    blocks=[
        TemplateBlock(
            id="header",
            type="text",
            x=50,
            y=30,
            width=800,
            height=60,
            content={"text": "[CHART] Analytics Dashboard", "size": "large"},
        ),
        TemplateBlock(
            id="revenue_metric",
            type="metric",
            x=50,
            y=120,
            width=200,
            height=120,
            content={
                "label": "Revenue",
                "value": "$125,000",
                "change": "+12%",
                "trend": "up",
            },
        ),
        TemplateBlock(
            id="users_metric",
            type="metric",
            x=280,
            y=120,
            width=200,
            height=120,
            content={
                "label": "Active Users",
                "value": "8,432",
                "change": "+5%",
                "trend": "up",
            },
        ),
        TemplateBlock(
            id="conversion_metric",
            type="metric",
            x=510,
            y=120,
            width=200,
            height=120,
            content={
                "label": "Conversion Rate",
                "value": "3.2%",
                "change": "-0.5%",
                "trend": "down",
            },
        ),
        TemplateBlock(
            id="chart_block",
            type="chart",
            x=50,
            y=270,
            width=500,
            height=300,
            content={
                "chart_type": "line",
                "title": "Revenue Trend",
                "data_source": "connected",
            },
        ),
        TemplateBlock(
            id="data_table",
            type="data",
            x=580,
            y=270,
            width=400,
            height=300,
            content={
                "title": "Top Products",
                "columns": ["Product", "Sales", "Revenue"],
            },
        ),
    ],
    tags=["analytics", "kpi", "dashboard", "charts"],
)

AI_WORKFLOW_TEMPLATE = CanvasTemplate(
    id=UUID("00000000-0000-0000-0000-000000000004"),
    name="AI Agent Workflow",
    description="Chain multiple AI agents together for complex tasks",
    category=TemplateCategory.AI_WORKFLOW,
    difficulty=TemplateDifficulty.ADVANCED,
    blocks=[
        TemplateBlock(
            id="input_block",
            type="agent_chat",
            x=50,
            y=200,
            width=300,
            height=200,
            content={
                "title": "User Input",
                "agent_type": "input",
                "system_prompt": "Extract key requirements from user input",
            },
        ),
        TemplateBlock(
            id="research_agent",
            type="agent_task",
            x=400,
            y=100,
            width=300,
            height=200,
            content={
                "title": "Research Agent",
                "task": "Gather information on the topic",
                "auto_execute": True,
            },
        ),
        TemplateBlock(
            id="analysis_agent",
            type="agent_task",
            x=400,
            y=350,
            width=300,
            height=200,
            content={
                "title": "Analysis Agent",
                "task": "Analyze and synthesize findings",
                "depends_on": ["research_agent"],
            },
        ),
        TemplateBlock(
            id="output_block",
            type="text",
            x=750,
            y=200,
            width=300,
            height=200,
            content={
                "title": "Final Output",
                "editable": True,
            },
        ),
    ],
    connections=[
        TemplateConnection("input_block", "research_agent"),
        TemplateConnection("input_block", "analysis_agent"),
        TemplateConnection("research_agent", "analysis_agent"),
        TemplateConnection("analysis_agent", "output_block"),
    ],
    tags=["ai", "agents", "workflow", "automation"],
)

MEETING_NOTES_TEMPLATE = CanvasTemplate(
    id=UUID("00000000-0000-0000-0000-000000000005"),
    name="Meeting Notes",
    description="Structured meeting notes with attendees, agenda, and action items",
    category=TemplateCategory.BUSINESS,
    difficulty=TemplateDifficulty.BEGINNER,
    blocks=[
        TemplateBlock(
            id="meeting_title",
            type="text",
            x=50,
            y=30,
            width=800,
            height=60,
            content={"text": "Meeting Title", "size": "large", "bold": True},
        ),
        TemplateBlock(
            id="attendees",
            type="text",
            x=50,
            y=110,
            width=350,
            height=150,
            content={
                "title": "[U+0001F465] Attendees",
                "text": "- \n- \n- ",
            },
        ),
        TemplateBlock(
            id="agenda",
            type="text",
            x=430,
            y=110,
            width=350,
            height=150,
            content={
                "title": "[LIST] Agenda",
                "text": "1. \n2. \n3. ",
            },
        ),
        TemplateBlock(
            id="notes",
            type="text",
            x=50,
            y=290,
            width=730,
            height=250,
            content={
                "title": "[NOTE] Notes",
                "text": "Key discussion points...",
            },
        ),
        TemplateBlock(
            id="action_items",
            type="task",
            x=50,
            y=570,
            width=730,
            height=150,
            content={
                "title": "[OK] Action Items",
                "tasks": [
                    {"text": "Action item 1", "assignee": "", "due": ""},
                ],
            },
        ),
    ],
    tags=["meeting", "notes", "collaboration"],
)

SQL_QUERY_BUILDER_TEMPLATE = CanvasTemplate(
    id=UUID("00000000-0000-0000-0000-000000000006"),
    name="SQL Query Builder",
    description="Visual SQL query construction with agent assistance",
    category=TemplateCategory.DATA_ANALYSIS,
    difficulty=TemplateDifficulty.INTERMEDIATE,
    blocks=[
        TemplateBlock(
            id="table_selector",
            type="data",
            x=50,
            y=50,
            width=250,
            height=200,
            content={
                "title": "Tables",
                "type": "table_list",
                "tables": ["users", "orders", "products"],
            },
        ),
        TemplateBlock(
            id="query_builder",
            type="agent_chat",
            x=350,
            y=50,
            width=400,
            height=300,
            content={
                "title": "SQL Assistant",
                "system_prompt": "Help construct SQL queries based on user requirements",
                "tools": ["schema_explorer", "query_validator"],
            },
        ),
        TemplateBlock(
            id="query_editor",
            type="code_executor",
            x=50,
            y=300,
            width=700,
            height=250,
            content={
                "language": "sql",
                "code": "SELECT * FROM users LIMIT 10;",
            },
        ),
        TemplateBlock(
            id="results",
            type="data",
            x=50,
            y=580,
            width=700,
            height=200,
            content={
                "title": "Query Results",
                "type": "query_results",
            },
        ),
    ],
    connections=[
        TemplateConnection("query_builder", "query_editor", label="generates"),
        TemplateConnection("query_editor", "results", label="outputs"),
    ],
    tags=["sql", "database", "queries", "data"],
)


class TemplateRegistry:
    """
    Registry for canvas templates.

    Manages built-in templates and user-created custom templates.
    """

    def __init__(self) -> None:
        self._templates: dict[UUID, CanvasTemplate] = {}
        self._category_index: dict[TemplateCategory, list[UUID]] = {}
        self._tag_index: dict[str, list[UUID]] = {}

        # Register built-in templates
        self._register_builtin_templates()

        logger.info(f"TemplateRegistry initialized with {len(self._templates)} templates")

    def _register_builtin_templates(self) -> None:
        """Register all built-in templates."""
        builtins = [
            BLANK_TEMPLATE,
            PROJECT_KANBAN_TEMPLATE,
            DATA_DASHBOARD_TEMPLATE,
            AI_WORKFLOW_TEMPLATE,
            MEETING_NOTES_TEMPLATE,
            SQL_QUERY_BUILDER_TEMPLATE,
        ]

        for template in builtins:
            self.register(template)

    def register(self, template: CanvasTemplate) -> None:
        """Register a new template."""
        self._templates[template.id] = template

        # Index by category
        if template.category not in self._category_index:
            self._category_index[template.category] = []
        if template.id not in self._category_index[template.category]:
            self._category_index[template.category].append(template.id)

        # Index by tags
        for tag in template.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            if template.id not in self._tag_index[tag]:
                self._tag_index[tag].append(template.id)

        logger.debug(f"Registered template: {template.name} ({template.id})")

    def unregister(self, template_id: UUID) -> CanvasTemplate | None:
        """Unregister a template."""
        template = self._templates.pop(template_id, None)
        if template:
            # Remove from indexes
            if template.category in self._category_index:
                self._category_index[template.category].remove(template_id)
            for tag in template.tags:
                if tag in self._tag_index:
                    self._tag_index[tag].remove(template_id)

        return template

    def get(self, template_id: UUID) -> CanvasTemplate | None:
        """Get template by ID."""
        return self._templates.get(template_id)

    def get_by_name(self, name: str) -> CanvasTemplate | None:
        """Get template by name (case-insensitive)."""
        name_lower = name.lower()
        for template in self._templates.values():
            if template.name.lower() == name_lower:
                return template
        return None

    def list_templates(
        self,
        category: TemplateCategory | None = None,
        difficulty: TemplateDifficulty | None = None,
        tags: list[str] | None = None,
        search: str | None = None,
        limit: int | None = None,
    ) -> list[CanvasTemplate]:
        """
        List templates with optional filtering.

        Args:
            category: Filter by category
            difficulty: Filter by difficulty level
            tags: Filter by tags (all must match)
            search: Search in name and description
            limit: Maximum number of templates to return
        """
        templates = list(self._templates.values())

        # Apply filters
        if category:
            templates = [t for t in templates if t.category == category]

        if difficulty:
            templates = [t for t in templates if t.difficulty == difficulty]

        if tags:
            templates = [t for t in templates if all(tag in t.tags for tag in tags)]

        if search:
            search_lower = search.lower()
            templates = [
                t
                for t in templates
                if (search_lower in t.name.lower() or search_lower in t.description.lower())
            ]

        # Sort by name
        templates.sort(key=lambda t: t.name)

        # Apply limit if specified
        if limit is not None and limit > 0:
            templates = templates[:limit]

        return templates

    def get_categories(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get all categories with counts."""
        return [
            {
                "id": cat.value,
                "name": cat.value.replace("_", " ").title(),
                "count": len(self._category_index.get(cat, [])),
            }
            for cat in TemplateCategory
        ]

    def get_tags(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get all tags with counts."""
        return [
            {"name": tag, "count": len(template_ids)}
            for tag, template_ids in self._tag_index.items()
        ]

    def apply_template(
        self,
        template_id: UUID,
        canvas_id: UUID,
        customizations: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Apply a template to create canvas content.

        Returns a dictionary with blocks and connections ready to be
        inserted into a canvas.
        """
        template = self.get(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")

        # Generate new IDs for blocks (avoid conflicts)
        id_mapping: dict[str, str] = {}
        blocks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for block in template.blocks:
            new_id = str(uuid4())
            id_mapping[block.id] = new_id

            # Apply customizations
            content = dict(block.content)
            if customizations and block.id in customizations:
                content.update(customizations[block.id])

            blocks.append(
                {
                    "id": new_id,
                    "type": block.type,
                    "x": block.x,
                    "y": block.y,
                    "width": block.width,
                    "height": block.height,
                    "content": content,
                    "style": block.style,
                }
            )

        # Map connection IDs
        connections: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for conn in template.connections:
            if conn.source_block_id in id_mapping and conn.target_block_id in id_mapping:
                connections.append(
                    {
                        "id": str(uuid4()),
                        "source_block_id": id_mapping[conn.source_block_id],
                        "target_block_id": id_mapping[conn.target_block_id],
                        "type": conn.connection_type,
                        "label": conn.label,
                        "style": conn.style,
                    }
                )

        return {
            "template_id": str(template_id),
            "template_name": template.name,
            "blocks": blocks,
            "connections": connections,
            "metadata": {
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "customizations": customizations or {},
            },
        }


# Global template registry
template_registry = TemplateRegistry()


class TemplateCreateRequest(BaseModel):
    """Request to create a custom template."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    category: TemplateCategory = TemplateCategory.CUSTOM
    difficulty: TemplateDifficulty = TemplateDifficulty.INTERMEDIATE
    blocks: list[dict[str, Any]] = Field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    connections: list[dict[str, Any]] = Field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    tags: list[str] = Field(default_factory=list)


class TemplateUpdateRequest(BaseModel):
    """Request to update a template."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    category: TemplateCategory | None = None
    difficulty: TemplateDifficulty | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
