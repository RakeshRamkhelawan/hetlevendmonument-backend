"""
Operational Transformation Engine

Implements OT algorithms for conflict-free collaborative editing.
Based on the ot.js protocol and Google Docs OT approach.

Key concepts:
- Operations are transformed against each other to maintain consistency
- Revision history tracks all operations
- Server is the single source of truth
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from loguru import logger


class OperationType(str, Enum):
    """Types of canvas operations."""

    INSERT_BLOCK = "insert_block"
    UPDATE_BLOCK = "update_block"
    DELETE_BLOCK = "delete_block"
    MOVE_BLOCK = "move_block"
    INSERT_CONNECTION = "insert_connection"
    DELETE_CONNECTION = "delete_connection"
    UPDATE_CANVAS = "update_canvas"


@dataclass
class Operation:
    """Base class for canvas operations."""

    type: OperationType
    target_id: UUID | None  # Block/connection ID, None for canvas
    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize operation to dict."""
        return {
            "type": self.type.value,
            "target_id": str(self.target_id) if self.target_id else None,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Operation":  # TODO(TYPE): replace Any with concrete type
        """Deserialize operation from dict."""
        return cls(
            type=OperationType(data["type"]),
            target_id=UUID(data["target_id"]) if data.get("target_id") else None,
            data=data["data"],
        )


@dataclass
class TransformedOperation:
    """Result of transforming an operation."""

    operation: Operation
    # If True, this operation was modified during transformation
    was_transformed: bool = False
    # Description of transformation applied
    transformation_log: list[str] = field(default_factory=list)


class OTTransformError(Exception):
    """Error during operational transformation."""

    pass


class OTEngine:
    """
    Operational Transformation Engine

    Handles transforming concurrent operations so they can be applied
    in sequence without conflicts.
    """

    def __init__(self) -> None:
        self.transformers = {
            # Define transformation rules for operation pairs
            # Format: (op1_type, op2_type) -> transform_function
            (OperationType.INSERT_BLOCK, OperationType.INSERT_BLOCK): self._transform_insert_insert,
            (OperationType.INSERT_BLOCK, OperationType.MOVE_BLOCK): self._transform_insert_move,
            (OperationType.INSERT_BLOCK, OperationType.DELETE_BLOCK): self._transform_insert_delete,
            (OperationType.MOVE_BLOCK, OperationType.MOVE_BLOCK): self._transform_move_move,
            (OperationType.MOVE_BLOCK, OperationType.DELETE_BLOCK): self._transform_move_delete,
            (OperationType.UPDATE_BLOCK, OperationType.UPDATE_BLOCK): self._transform_update_update,
            (OperationType.UPDATE_BLOCK, OperationType.MOVE_BLOCK): self._transform_update_move,
            (OperationType.DELETE_BLOCK, OperationType.DELETE_BLOCK): self._transform_delete_delete,
        }

    def transform(
        self,
        operation: Operation,
        against: Operation,
        priority: str = "server",
    ) -> TransformedOperation:
        """
        Transform an operation against another concurrent operation.

        Args:
            operation: The operation to transform (client's operation)
            against: The operation to transform against (server's operation)
            priority: Which operation has priority ("server" or "client")

        Returns:
            TransformedOperation with the modified operation
        """
        # If operations target different objects, no transformation needed
        if operation.target_id != against.target_id:
            # Different targets - operations are independent
            return TransformedOperation(operation=operation)

        # If same target, apply type-specific transformation
        key = (operation.type, against.type)

        if key in self.transformers:
            try:
                return self.transformers[key](operation, against, priority)
            except Exception as e:
                logger.error(f"OT transformation error: {e}")
                # Return original operation as fallback
                return TransformedOperation(operation=operation)

        # No transformer found - return as-is (may cause conflicts)
        logger.warning(f"No transformer for {key}")
        return TransformedOperation(operation=operation)

    def transform_against_many(
        self,
        operation: Operation,
        server_operations: list[Operation],
        priority: str = "server",
    ) -> TransformedOperation:
        """
        Transform an operation against a list of server operations.

        This is used when a client operation arrives and needs to be
        transformed against all server operations that occurred since
        the client's last sync.
        """
        current_op = operation
        logs: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for server_op in server_operations:
            result = self.transform(current_op, server_op, priority)
            current_op = result.operation
            logs.extend(result.transformation_log)

        return TransformedOperation(
            operation=current_op,
            was_transformed=len(logs) > 0,
            transformation_log=logs,
        )

    # =========================================================================
    # Transform Implementations
    # =========================================================================

    def _transform_insert_insert(
        self,
        op1: Operation,
        op2: Operation,
        priority: str,
    ) -> TransformedOperation:
        """
        Transform two insert operations.

        If two clients insert blocks at the same position,
        we need to decide which one goes first based on priority.
        """
        # Extract positions
        pos1 = op1.data.get("position", {})
        pos2 = op2.data.get("position", {})

        # If positions are different, no conflict
        if pos1 != pos2:
            return TransformedOperation(operation=op1)

        # Same position - use priority to break tie
        if priority == "server":
            # Server wins - client operation gets offset slightly
            new_data = dict(op1.data)
            new_data["position"] = {
                "x": pos1.get("x", 0) + 10,
                "y": pos1.get("y", 0) + 10,
            }
            return TransformedOperation(
                operation=Operation(
                    type=op1.type,
                    target_id=op1.target_id,
                    data=new_data,
                ),
                was_transformed=True,
                transformation_log=["Offset position due to concurrent insert"],
            )

        return TransformedOperation(operation=op1)

    def _transform_insert_move(
        self,
        op1: Operation,
        op2: Operation,
        priority: str,
    ) -> TransformedOperation:
        """Transform insert against move."""
        # Insert is independent of move - no transformation needed
        return TransformedOperation(operation=op1)

    def _transform_insert_delete(
        self,
        op1: Operation,
        op2: Operation,
        priority: str,
    ) -> TransformedOperation:
        """Transform insert against delete."""
        # Insert creates a new block, delete removes one
        # These are independent unless they're the same block
        if op1.target_id == op2.target_id:
            # Cannot insert a block that's being deleted
            # Convert to no-op
            return TransformedOperation(
                operation=Operation(
                    type=op1.type,
                    target_id=op1.target_id,
                    data={"noop": True, **op1.data},
                ),
                was_transformed=True,
                transformation_log=["Converted to no-op: target being deleted"],
            )
        return TransformedOperation(operation=op1)

    def _transform_move_move(
        self,
        op1: Operation,
        op2: Operation,
        priority: str,
    ) -> TransformedOperation:
        """
        Transform two move operations on the same block.

        If both clients move the same block, server wins.
        """
        if op1.target_id == op2.target_id:
            if priority == "server":
                # Server wins - client move is discarded
                return TransformedOperation(
                    operation=Operation(
                        type=op1.type,
                        target_id=op1.target_id,
                        data={"noop": True, **op1.data},
                    ),
                    was_transformed=True,
                    transformation_log=["Discarded: server move takes precedence"],
                )

        return TransformedOperation(operation=op1)

    def _transform_move_delete(
        self,
        op1: Operation,
        op2: Operation,
        priority: str,
    ) -> TransformedOperation:
        """Transform move against delete."""
        if op1.target_id == op2.target_id:
            # Cannot move a deleted block
            return TransformedOperation(
                operation=Operation(
                    type=op1.type,
                    target_id=op1.target_id,
                    data={"noop": True, **op1.data},
                ),
                was_transformed=True,
                transformation_log=["Converted to no-op: target being deleted"],
            )
        return TransformedOperation(operation=op1)

    def _transform_update_update(
        self,
        op1: Operation,
        op2: Operation,
        priority: str,
    ) -> TransformedOperation:
        """
        Transform two update operations on the same block.

        Merge the updates if they touch different fields.
        If same field, server wins.
        """
        if op1.target_id != op2.target_id:
            return TransformedOperation(operation=op1)

        data1 = op1.data
        data2 = op2.data

        # Find conflicting fields
        conflicts = set(data1.keys()) & set(data2.keys())

        if not conflicts:
            # No conflicts - both updates can apply
            return TransformedOperation(operation=op1)

        if priority == "server":
            # Server wins on conflicts
            new_data = {k: v for k, v in data1.items() if k not in conflicts}
            if new_data:
                return TransformedOperation(
                    operation=Operation(
                        type=op1.type,
                        target_id=op1.target_id,
                        data=new_data,
                    ),
                    was_transformed=True,
                    transformation_log=[f"Removed conflicting fields: {conflicts}"],
                )
            else:
                # All fields conflict - operation becomes no-op
                return TransformedOperation(
                    operation=Operation(
                        type=op1.type,
                        target_id=op1.target_id,
                        data={"noop": True},
                    ),
                    was_transformed=True,
                    transformation_log=["Converted to no-op: all fields conflict"],
                )

        return TransformedOperation(operation=op1)

    def _transform_update_move(
        self,
        op1: Operation,
        op2: Operation,
        priority: str,
    ) -> TransformedOperation:
        """Transform update against move."""
        # Update and move are independent
        # (update changes content, move changes position)
        return TransformedOperation(operation=op1)

    def _transform_delete_delete(
        self,
        op1: Operation,
        op2: Operation,
        priority: str,
    ) -> TransformedOperation:
        """Transform two delete operations."""
        if op1.target_id == op2.target_id:
            # Both deleting same block - second delete is no-op
            return TransformedOperation(
                operation=Operation(
                    type=op1.type,
                    target_id=op1.target_id,
                    data={"noop": True, **op1.data},
                ),
                was_transformed=True,
                transformation_log=["Already deleted"],
            )
        return TransformedOperation(operation=op1)


class CompositionEngine:
    """
    Composes multiple operations into a single operation.

    Used to batch operations and reduce sync overhead.
    """

    def compose(self, op1: Operation, op2: Operation) -> Operation | None:
        """
        Compose two operations into one.

        Returns None if operations cannot be composed.
        """
        # Only compose operations on the same target
        if op1.target_id != op2.target_id:
            return None

        # Compose updates on same target
        if op1.type == OperationType.UPDATE_BLOCK and op2.type == OperationType.UPDATE_BLOCK:
            # Merge the updates
            merged_data = {**op1.data, **op2.data}
            return Operation(
                type=OperationType.UPDATE_BLOCK,
                target_id=op1.target_id,
                data=merged_data,
            )

        # Compose moves on same target
        if op1.type == OperationType.MOVE_BLOCK and op2.type == OperationType.MOVE_BLOCK:
            # Use the final position
            return Operation(
                type=OperationType.MOVE_BLOCK,
                target_id=op1.target_id,
                data=op2.data,  # Last position wins
            )

        return None

    def compose_many(self, operations: list[Operation]) -> list[Operation]:
        """
        Compose a list of operations into fewer operations.

        Returns the optimized list of operations.
        """
        if len(operations) < 2:
            return operations

        result = [operations[0]]

        for op in operations[1:]:
            composed = self.compose(result[-1], op)
            if composed:
                result[-1] = composed
            else:
                result.append(op)

        return result


# Global OT engine instance
ot_engine = OTEngine()
composition_engine = CompositionEngine()
