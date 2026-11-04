"""
Tests for Canvas domain models.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from src.domains.canvas.models import (
    BlockType,
    Canvas,
    CanvasBlock,
    CanvasCollaborator,
    CanvasConnection,
    CanvasOperation,
    CollaboratorRole,
)


class TestCanvasModel:
    """Test Canvas SQLAlchemy model."""

    def test_canvas_creation(self):
        """Test basic canvas creation."""
        canvas = Canvas(
            id=uuid4(),
            tenant_id=1,
            owner_id=uuid4(),
            name="Test Canvas",
            template="blank",
            is_public=False,
        )

        assert canvas.name == "Test Canvas"
        assert canvas.template == "blank"
        assert canvas.is_public is False
        # version is set by database default, not in Python

    def test_canvas_relationships(self):
        """Test canvas relationships are initialized."""
        canvas = Canvas(
            id=uuid4(),
            tenant_id=1,
            owner_id=uuid4(),
            name="Test Canvas",
        )

        # Relationships should be empty lists initially
        assert canvas.blocks == []
        assert canvas.connections == []
        assert canvas.collaborators == []


class TestCanvasBlockModel:
    """Test CanvasBlock SQLAlchemy model."""

    def test_block_creation(self):
        """Test basic block creation."""
        block = CanvasBlock(
            id=uuid4(),
            canvas_id=uuid4(),
            type=BlockType.TEXT.value,
            x=Decimal("100.00"),
            y=Decimal("200.00"),
            width=Decimal("300.00"),
            height=Decimal("150.00"),
            content={"text": "Hello World"},
            created_by=uuid4(),
        )

        assert block.type == "text"
        assert float(block.x) == 100.0
        assert float(block.y) == 200.0
        assert block.content == {"text": "Hello World"}

    def test_block_types(self):
        """Test all block types are valid."""
        for block_type in BlockType:
            block = CanvasBlock(
                id=uuid4(),
                canvas_id=uuid4(),
                type=block_type.value,
                x=Decimal("0.00"),
                y=Decimal("0.00"),
                width=Decimal("100.00"),
                height=Decimal("100.00"),
                created_by=uuid4(),
            )
            assert block.type == block_type.value


class TestCanvasConnectionModel:
    """Test CanvasConnection SQLAlchemy model."""

    def test_connection_creation(self):
        """Test basic connection creation."""
        conn = CanvasConnection(
            id=uuid4(),
            canvas_id=uuid4(),
            from_block_id=uuid4(),
            to_block_id=uuid4(),
            connection_type="straight",
            is_bidirectional=False,
        )

        assert conn.connection_type == "straight"
        assert conn.is_bidirectional is False


class TestCanvasCollaboratorModel:
    """Test CanvasCollaborator SQLAlchemy model."""

    def test_collaborator_creation(self):
        """Test basic collaborator creation."""
        collab = CanvasCollaborator(
            id=uuid4(),
            canvas_id=uuid4(),
            user_id=uuid4(),
            role=CollaboratorRole.EDITOR.value,
            added_by=uuid4(),
        )

        assert collab.role == "editor"

    def test_collaborator_roles(self):
        """Test all collaborator roles."""
        for role in CollaboratorRole:
            collab = CanvasCollaborator(
                id=uuid4(),
                canvas_id=uuid4(),
                user_id=uuid4(),
                role=role.value,
                added_by=uuid4(),
            )
            assert collab.role == role.value


class TestCanvasOperationModel:
    """Test CanvasOperation SQLAlchemy model."""

    def test_operation_creation(self):
        """Test basic operation creation."""
        op = CanvasOperation(
            id=uuid4(),
            canvas_id=uuid4(),
            operation_type="insert",
            target_type="block",
            target_id=uuid4(),
            data={"x": 100, "y": 200},
            client_id="client_123",
            revision=1,
        )

        assert op.operation_type == "insert"
        assert op.target_type == "block"
        assert op.revision == 1
