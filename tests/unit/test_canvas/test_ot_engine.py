"""
Tests for Operational Transformation Engine.
"""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.domains.canvas.ot_engine import (
    CompositionEngine,
    Operation,
    OperationType,
    OTEngine,
    TransformedOperation,
    composition_engine,
    ot_engine,
)


class TestOperation:
    """Test Operation dataclass."""

    def test_operation_creation(self):
        """Test basic operation creation."""
        op = Operation(
            type=OperationType.INSERT_BLOCK,
            target_id=uuid4(),
            data={"x": 100, "y": 200},
        )

        assert op.type == OperationType.INSERT_BLOCK
        assert op.data == {"x": 100, "y": 200}

    def test_operation_to_dict(self):
        """Test operation serialization."""
        target_id = uuid4()
        op = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=target_id,
            data={"text": "Hello"},
        )

        data = op.to_dict()
        assert data["type"] == "update_block"
        assert data["target_id"] == str(target_id)
        assert data["data"] == {"text": "Hello"}

    def test_operation_from_dict(self):
        """Test operation deserialization."""
        target_id = uuid4()
        data = {
            "type": "move_block",
            "target_id": str(target_id),
            "data": {"x": 100, "y": 200},
        }

        op = Operation.from_dict(data)
        assert op.type == OperationType.MOVE_BLOCK
        assert op.target_id == target_id
        assert op.data == {"x": 100, "y": 200}


class TestOTEngineInsertInsert:
    """Test OT transformations for insert-insert conflicts."""

    def test_insert_different_positions_no_conflict(self):
        """Two inserts at different positions - no transformation needed."""
        op1 = Operation(
            type=OperationType.INSERT_BLOCK,
            target_id=uuid4(),
            data={"position": {"x": 100, "y": 100}},
        )
        op2 = Operation(
            type=OperationType.INSERT_BLOCK,
            target_id=uuid4(),
            data={"position": {"x": 200, "y": 200}},
        )

        result = ot_engine.transform(op1, op2, priority="server")

        assert not result.was_transformed
        assert result.operation.data["position"]["x"] == 100

    def test_insert_same_position_server_priority(self):
        """Two inserts at same position with server priority."""
        # Note: Insert operations with same target_id (same block being inserted twice)
        target_id = uuid4()
        op1 = Operation(
            type=OperationType.INSERT_BLOCK,
            target_id=target_id,
            data={"position": {"x": 100, "y": 100}},
        )
        op2 = Operation(
            type=OperationType.INSERT_BLOCK,
            target_id=target_id,  # Same target - duplicate insert
            data={"position": {"x": 100, "y": 100}},  # Same position
        )

        result = ot_engine.transform(op1, op2, priority="server")

        # Client operation should be offset
        assert result.was_transformed
        assert result.operation.data["position"]["x"] == 110  # Offset by 10
        assert result.operation.data["position"]["y"] == 110


class TestOTEngineUpdateUpdate:
    """Test OT transformations for update-update conflicts."""

    def test_update_different_fields_no_conflict(self):
        """Updates on different fields - no transformation needed."""
        target_id = uuid4()
        op1 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=target_id,
            data={"text": "Hello"},
        )
        op2 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=target_id,
            data={"color": "red"},  # Different field
        )

        result = ot_engine.transform(op1, op2, priority="server")

        assert not result.was_transformed
        assert "text" in result.operation.data

    def test_update_same_field_server_priority(self):
        """Updates on same field with server priority."""
        target_id = uuid4()
        op1 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=target_id,
            data={"text": "Client Text", "color": "blue"},
        )
        op2 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=target_id,
            data={"text": "Server Text"},  # Same field conflict
        )

        result = ot_engine.transform(op1, op2, priority="server")

        # Server wins on conflict, but non-conflicting fields remain
        assert result.was_transformed
        assert "text" not in result.operation.data  # Conflicting field removed
        assert "color" in result.operation.data  # Non-conflicting field kept

    def test_update_all_fields_conflict_becomes_noop(self):
        """When all fields conflict, operation becomes no-op."""
        target_id = uuid4()
        op1 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=target_id,
            data={"text": "Client"},
        )
        op2 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=target_id,
            data={"text": "Server"},  # Same field
        )

        result = ot_engine.transform(op1, op2, priority="server")

        assert result.was_transformed
        assert result.operation.data.get("noop") is True


class TestOTEngineMoveMove:
    """Test OT transformations for move-move conflicts."""

    def test_move_different_blocks_no_conflict(self):
        """Moves on different blocks - no transformation needed."""
        op1 = Operation(
            type=OperationType.MOVE_BLOCK,
            target_id=uuid4(),
            data={"position": {"x": 100, "y": 100}},
        )
        op2 = Operation(
            type=OperationType.MOVE_BLOCK,
            target_id=uuid4(),  # Different block
            data={"position": {"x": 200, "y": 200}},
        )

        result = ot_engine.transform(op1, op2, priority="server")

        assert not result.was_transformed

    def test_move_same_block_server_priority(self):
        """Moves on same block with server priority."""
        target_id = uuid4()
        op1 = Operation(
            type=OperationType.MOVE_BLOCK,
            target_id=target_id,
            data={"position": {"x": 100, "y": 100}},
        )
        op2 = Operation(
            type=OperationType.MOVE_BLOCK,
            target_id=target_id,  # Same block
            data={"position": {"x": 200, "y": 200}},
        )

        result = ot_engine.transform(op1, op2, priority="server")

        # Client move is discarded
        assert result.was_transformed
        assert result.operation.data.get("noop") is True


class TestOTEngineMoveDelete:
    """Test OT transformations for move-delete conflicts."""

    def test_move_deleted_block_becomes_noop(self):
        """Moving a deleted block becomes no-op."""
        target_id = uuid4()
        op1 = Operation(
            type=OperationType.MOVE_BLOCK,
            target_id=target_id,
            data={"position": {"x": 100, "y": 100}},
        )
        op2 = Operation(
            type=OperationType.DELETE_BLOCK,
            target_id=target_id,  # Same block being deleted
            data={},
        )

        result = ot_engine.transform(op1, op2, priority="server")

        assert result.was_transformed
        assert result.operation.data.get("noop") is True


class TestOTEngineDeleteDelete:
    """Test OT transformations for delete-delete conflicts."""

    def test_delete_same_block_second_becomes_noop(self):
        """Deleting an already deleted block becomes no-op."""
        target_id = uuid4()
        op1 = Operation(
            type=OperationType.DELETE_BLOCK,
            target_id=target_id,
            data={},
        )
        op2 = Operation(
            type=OperationType.DELETE_BLOCK,
            target_id=target_id,  # Same block
            data={},
        )

        result = ot_engine.transform(op1, op2, priority="server")

        assert result.was_transformed
        assert result.operation.data.get("noop") is True


class TestOTEngineTransformMany:
    """Test transforming against multiple operations."""

    def test_transform_against_many_operations(self):
        """Transform one operation against multiple server operations."""
        target_id = uuid4()

        # Client operation
        client_op = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=target_id,
            data={"text": "Client", "color": "blue", "size": 12},
        )

        # Multiple server operations
        server_ops = [
            Operation(
                type=OperationType.UPDATE_BLOCK,
                target_id=target_id,
                data={"text": "Server"},  # Conflict
            ),
            Operation(
                type=OperationType.UPDATE_BLOCK,
                target_id=target_id,
                data={"font": "Arial"},  # No conflict
            ),
        ]

        result = ot_engine.transform_against_many(client_op, server_ops, priority="server")

        # Should remove conflicting field but keep non-conflicting ones
        assert result.was_transformed
        assert "text" not in result.operation.data
        assert "color" in result.operation.data
        assert "size" in result.operation.data


class TestCompositionEngine:
    """Test operation composition."""

    def test_compose_updates_same_target(self):
        """Compose two updates on same target."""
        target_id = uuid4()
        op1 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=target_id,
            data={"text": "Hello"},
        )
        op2 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=target_id,
            data={"color": "red"},
        )

        composed = composition_engine.compose(op1, op2)

        assert composed is not None
        assert composed.data["text"] == "Hello"
        assert composed.data["color"] == "red"

    def test_compose_moves_same_target(self):
        """Compose two moves on same target."""
        target_id = uuid4()
        op1 = Operation(
            type=OperationType.MOVE_BLOCK,
            target_id=target_id,
            data={"position": {"x": 100, "y": 100}},
        )
        op2 = Operation(
            type=OperationType.MOVE_BLOCK,
            target_id=target_id,
            data={"position": {"x": 200, "y": 200}},
        )

        composed = composition_engine.compose(op1, op2)

        assert composed is not None
        # Last position wins
        assert composed.data["position"]["x"] == 200

    def test_cannot_compose_different_targets(self):
        """Cannot compose operations on different targets."""
        op1 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=uuid4(),
            data={"text": "Hello"},
        )
        op2 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=uuid4(),  # Different target
            data={"text": "World"},
        )

        composed = composition_engine.compose(op1, op2)

        assert composed is None

    def test_compose_many_operations(self):
        """Compose a list of operations."""
        target_id = uuid4()
        operations = [
            Operation(
                type=OperationType.UPDATE_BLOCK,
                target_id=target_id,
                data={"a": 1},
            ),
            Operation(
                type=OperationType.UPDATE_BLOCK,
                target_id=target_id,
                data={"b": 2},
            ),
            Operation(
                type=OperationType.UPDATE_BLOCK,
                target_id=target_id,
                data={"c": 3},
            ),
        ]

        result = composition_engine.compose_many(operations)

        # Should be composed into one operation
        assert len(result) == 1
        assert result[0].data == {"a": 1, "b": 2, "c": 3}


class TestOTEngineDifferentTargets:
    """Test that operations on different targets are independent."""

    def test_operations_on_different_targets_no_transform(self):
        """Operations on different targets don't need transformation."""
        op1 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=uuid4(),
            data={"text": "Block 1"},
        )
        op2 = Operation(
            type=OperationType.UPDATE_BLOCK,
            target_id=uuid4(),  # Different target
            data={"text": "Block 2"},
        )

        result = ot_engine.transform(op1, op2, priority="server")

        assert not result.was_transformed
        assert result.operation.data["text"] == "Block 1"
