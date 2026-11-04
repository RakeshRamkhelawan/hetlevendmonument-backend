"""
Canvas Revision Manager

Manages the revision history of canvas operations.
Tracks all changes, supports point-in-time recovery,
and enables operational transformation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.canvas.models import CanvasOperation
from src.domains.canvas.ot_engine import Operation, OperationType, ot_engine


@dataclass
class Revision:
    """A single revision in the canvas history."""

    revision_number: int
    operation: Operation
    client_id: str
    timestamp: datetime
    # If this revision was transformed from original
    transformed_from: int | None = None
    transformation_log: list[str] = field(default_factory=list)


@dataclass
class SyncState:
    """Client synchronization state."""

    client_id: str
    canvas_id: UUID
    last_revision: int  # Last revision client has acknowledged
    pending_operations: list[Operation] = field(default_factory=list)


class RevisionManager:
    """
    Manages canvas revision history.

    Responsibilities:
    - Store all operations in order
    - Track client sync states
    - Provide operations for transformation
    - Support undo/redo functionality
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        # In-memory cache of recent revisions per canvas
        self._revision_cache: dict[UUID, list[Revision]] = {}
        self._client_states: dict[str, SyncState] = {}

    async def add_operation(
        self,
        canvas_id: UUID,
        operation: Operation,
        client_id: str,
        transformed_from: int | None = None,
        transformation_log: list[str] | None = None,
    ) -> int:
        """
        Add an operation to the revision history.

        Returns the assigned revision number.
        """
        # Get next revision number
        result = await self.db.execute(
            select(CanvasOperation)
            .where(CanvasOperation.canvas_id == canvas_id)
            .order_by(CanvasOperation.revision.desc())
            .limit(1)
        )
        last_op = result.scalar_one_or_none()
        next_revision = (last_op.revision + 1) if last_op else 1

        # Store in database
        db_operation = CanvasOperation(
            canvas_id=canvas_id,
            operation_type=operation.type.value,
            target_type="block" if "block" in operation.type.value else "connection",
            target_id=operation.target_id,
            data=operation.data,
            client_id=client_id,
            revision=next_revision,
        )

        self.db.add(db_operation)
        await self.db.commit()

        # Create revision object
        revision = Revision(
            revision_number=next_revision,
            operation=operation,
            client_id=client_id,
            timestamp=datetime.now(timezone.utc),
            transformed_from=transformed_from,
            transformation_log=transformation_log or [],
        )

        # Cache it
        if canvas_id not in self._revision_cache:
            self._revision_cache[canvas_id] = []
        self._revision_cache[canvas_id].append(revision)

        # Trim cache if too large (keep last 100)
        if len(self._revision_cache[canvas_id]) > 100:
            self._revision_cache[canvas_id] = self._revision_cache[canvas_id][-100:]

        # Update client state
        if client_id in self._client_states:
            self._client_states[client_id].last_revision = next_revision

        logger.debug(
            f"Added revision {next_revision} to canvas {canvas_id} from client {client_id}"
        )

        return next_revision

    async def get_operations_since(
        self,
        canvas_id: UUID,
        revision: int,
        limit: int = 100,
    ) -> list[Revision]:
        """
        Get all operations since a specific revision.

        Used by clients to catch up on missed operations.
        """
        # Check cache first
        if canvas_id in self._revision_cache:
            cached = self._revision_cache[canvas_id]
            result = [r for r in cached if r.revision_number > revision]
            if result:
                return result

        # Fetch from database
        db_result = await self.db.execute(
            select(CanvasOperation)
            .where(CanvasOperation.canvas_id == canvas_id)
            .where(CanvasOperation.revision > revision)
            .order_by(CanvasOperation.revision)
            .limit(limit)
        )

        operations = db_result.scalars().all()

        revisions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for op in operations:
            revision_obj = Revision(
                revision_number=op.revision,
                operation=Operation(
                    type=OperationType(op.operation_type),
                    target_id=op.target_id,
                    data=op.data,
                ),
                client_id=op.client_id,
                timestamp=op.created_at,
            )
            revisions.append(revision_obj)

        return revisions

    async def get_latest_revision(self, canvas_id: UUID) -> int:
        """Get the latest revision number for a canvas."""
        result = await self.db.execute(
            select(CanvasOperation)
            .where(CanvasOperation.canvas_id == canvas_id)
            .order_by(CanvasOperation.revision.desc())
            .limit(1)
        )
        last_op = result.scalar_one_or_none()
        return last_op.revision if last_op else 0

    def register_client(self, client_id: str, canvas_id: UUID) -> None:
        """Register a new client for sync tracking."""
        self._client_states[client_id] = SyncState(
            client_id=client_id,
            canvas_id=canvas_id,
            last_revision=0,
        )
        logger.debug(f"Registered client {client_id} for canvas {canvas_id}")

    def unregister_client(self, client_id: str) -> None:
        """Unregister a client."""
        if client_id in self._client_states:
            del self._client_states[client_id]
            logger.debug(f"Unregistered client {client_id}")

    def update_client_revision(self, client_id: str, revision: int) -> None:
        """Update a client's last known revision."""
        if client_id in self._client_states:
            self._client_states[client_id].last_revision = revision

    async def process_client_operation(
        self,
        canvas_id: UUID,
        client_id: str,
        operation: Operation,
        client_revision: int,
    ) -> tuple[Revision, list[Revision]]:
        """
        Process an operation from a client.

        This:
        1. Gets all server operations the client hasn't seen
        2. Transforms the client operation against them
        3. Stores the transformed operation
        4. Returns the new revision + operations client needs

        Returns: Tuple[Any, ...] of (new_revision, operations_for_client)  # TODO(TYPE): replace Any with concrete type
        """
        # Get server operations client hasn't seen
        server_operations = await self.get_operations_since(canvas_id, client_revision)

        # Transform client operation against server operations
        transformed = ot_engine.transform_against_many(
            operation,
            [r.operation for r in server_operations],
            priority="server",
        )

        # Store transformed operation
        new_revision = await self.add_operation(
            canvas_id=canvas_id,
            operation=transformed.operation,
            client_id=client_id,
            transformed_from=client_revision if transformed.was_transformed else None,
            transformation_log=transformed.transformation_log,
        )

        # Create revision object for response
        revision = Revision(
            revision_number=new_revision,
            operation=transformed.operation,
            client_id=client_id,
            timestamp=datetime.now(timezone.utc),
            transformed_from=client_revision if transformed.was_transformed else None,
            transformation_log=transformed.transformation_log,
        )

        return revision, server_operations

    async def undo(self, canvas_id: UUID, steps: int = 1) -> Operation | None:
        """
        Undo the last N operations.

        Returns the inverse operation to apply, or None if cannot undo.
        """
        # Get recent operations
        recent = await self.get_operations_since(
            canvas_id,
            revision=await self.get_latest_revision(canvas_id) - steps,
        )

        if not recent:
            return None

        # Generate inverse operations
        # This is simplified - full implementation would track inverse operations
        last_op = recent[-1].operation

        if last_op.type == OperationType.INSERT_BLOCK:
            # Inverse of insert is delete
            return Operation(
                type=OperationType.DELETE_BLOCK,
                target_id=last_op.target_id,
                data={},
            )
        elif last_op.type == OperationType.DELETE_BLOCK:
            # Inverse of delete is insert (need to store full data)
            # This requires storing deleted block data
            return None
        elif last_op.type == OperationType.UPDATE_BLOCK:
            # Would need previous value stored
            return None

        return None

    async def get_history(
        self,
        canvas_id: UUID,
        start_revision: int = 1,
        end_revision: int | None = None,
    ) -> list[Revision]:
        """Get operation history for a canvas."""
        query = (
            select(CanvasOperation)
            .where(CanvasOperation.canvas_id == canvas_id)
            .where(CanvasOperation.revision >= start_revision)
            .order_by(CanvasOperation.revision)
        )

        if end_revision:
            query = query.where(CanvasOperation.revision <= end_revision)

        result = await self.db.execute(query)
        operations = result.scalars().all()

        return [
            Revision(
                revision_number=op.revision,
                operation=Operation(
                    type=OperationType(op.operation_type),
                    target_id=op.target_id,
                    data=op.data,
                ),
                client_id=op.client_id,
                timestamp=op.created_at,
            )
            for op in operations
        ]

    async def clear_cache(self, canvas_id: UUID | None = None) -> None:
        """Clear revision cache."""
        if canvas_id:
            self._revision_cache.pop(canvas_id, None)
        else:
            self._revision_cache.clear()
