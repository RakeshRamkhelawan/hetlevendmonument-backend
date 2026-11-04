"""
Tests for Canvas Pydantic schemas.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.domains.canvas.schemas import (
    AgentBlockContent,
    BlockCreate,
    BlockRead,
    BlockUpdate,
    CanvasCreate,
    CanvasRead,
    CanvasUpdate,
    CollaboratorCreate,
    ConnectionCreate,
    MetricBlockContent,
    Position,
    Size,
    TaskBlockContent,
    TextBlockContent,
    Viewport,
)


class TestPositionSchemas:
    """Test position/size schemas."""

    def test_position_creation(self):
        """Test Position schema."""
        pos = Position(x=Decimal("100.50"), y=Decimal("200.75"))
        assert float(pos.x) == 100.5
        assert float(pos.y) == 200.75

    def test_size_creation(self):
        """Test Size schema."""
        size = Size(width=Decimal("300.00"), height=Decimal("150.00"))
        assert float(size.width) == 300.0
        assert float(size.height) == 150.0

    def test_viewport_creation(self):
        """Test Viewport schema."""
        viewport = Viewport(x=Decimal("0.00"), y=Decimal("0.00"), zoom=Decimal("1.5"))
        assert float(viewport.zoom) == 1.5


class TestBlockContentSchemas:
    """Test block content schemas."""

    def test_text_block_content(self):
        """Test TextBlockContent schema."""
        content = TextBlockContent(text="Hello World", format="markdown")
        assert content.text == "Hello World"
        assert content.format == "markdown"

    def test_metric_block_content(self):
        """Test MetricBlockContent schema."""
        content = MetricBlockContent(
            metric_name="Revenue",
            current_value=100000.0,
            target_value=150000.0,
            unit="EUR",
            trend="up",
            chart_type="line",
        )
        assert content.metric_name == "Revenue"
        assert content.current_value == 100000.0
        assert content.trend == "up"

    def test_agent_block_content(self):
        """Test AgentBlockContent schema."""
        content = AgentBlockContent(
            agent_id=uuid4(),
            agent_name="Data Analyzer",
            status="running",
            progress=50.0,
        )
        assert content.agent_name == "Data Analyzer"
        assert content.progress == 50.0

    def test_task_block_content(self):
        """Test TaskBlockContent schema."""
        content = TaskBlockContent(
            title="My Task",
            description="Task description",
            status="in_progress",
        )
        assert content.title == "My Task"
        assert content.status == "in_progress"


class TestBlockSchemas:
    """Test block CRUD schemas."""

    def test_block_create(self):
        """Test BlockCreate schema."""
        block = BlockCreate(
            type="text",
            position=Position(x=Decimal("100.00"), y=Decimal("200.00")),
            size=Size(width=Decimal("300.00"), height=Decimal("150.00")),
            z_index=1,
            content={"text": "Hello"},
        )
        assert block.type == "text"
        assert block.z_index == 1

    def test_block_update(self):
        """Test BlockUpdate schema."""
        update = BlockUpdate(
            position=Position(x=Decimal("150.00"), y=Decimal("250.00")),
            content={"text": "Updated"},
        )
        assert update.position.x == Decimal("150.00")
        assert update.content == {"text": "Updated"}


class TestCanvasSchemas:
    """Test canvas CRUD schemas."""

    def test_canvas_create(self):
        """Test CanvasCreate schema."""
        canvas = CanvasCreate(
            name="My Canvas",
            template="strategy",
            is_public=True,
        )
        assert canvas.name == "My Canvas"
        assert canvas.template == "strategy"
        assert canvas.is_public is True

    def test_canvas_create_validation(self):
        """Test CanvasCreate validation."""
        # Name is required
        with pytest.raises(ValueError):
            CanvasCreate(name="", template="blank")

    def test_canvas_update(self):
        """Test CanvasUpdate schema."""
        update = CanvasUpdate(name="Updated Name")
        assert update.name == "Updated Name"
        assert update.is_public is None  # Optional field


class TestCollaboratorSchemas:
    """Test collaborator schemas."""

    def test_collaborator_create(self):
        """Test CollaboratorCreate schema."""
        collab = CollaboratorCreate(
            user_id=uuid4(),
            role="editor",
        )
        assert collab.role == "editor"


class TestConnectionSchemas:
    """Test connection schemas."""

    def test_connection_create(self):
        """Test ConnectionCreate schema."""
        conn = ConnectionCreate(
            from_block_id=uuid4(),
            to_block_id=uuid4(),
            connection_type="curved",
            label="Depends on",
        )
        assert conn.connection_type == "curved"
        assert conn.label == "Depends on"
