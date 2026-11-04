"""
Canvas Service Layer

Business logic for canvas operations including CRUD, collaboration,
and agent integration.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError, PermissionDeniedError
from src.domains.canvas.models import (
    BlockType,
    Canvas,
    CanvasBlock,
    CanvasCollaborator,
    CanvasConnection,
    CanvasOperation,
    CollaboratorRole,
)
from src.domains.canvas.schemas import (
    BlockCreate,
    BlockRead,
    BlockUpdate,
    CanvasCreate,
    CanvasRead,
    CanvasUpdate,
    CollaboratorCreate,
    CollaboratorRead,
    ConnectionCreate,
    ConnectionRead,
)


class CanvasService:
    """Service for canvas operations."""

    def __init__(self, db: AsyncSession, tenant_id: int, user_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    # =============================================================================
    # Canvas CRUD
    # =============================================================================

    async def create_canvas(self, data: CanvasCreate) -> Canvas:
        """Create a new canvas."""
        canvas = Canvas(
            tenant_id=self.tenant_id,
            owner_id=self.user_id,
            name=data.name,
            template=data.template,
            is_public=data.is_public,
        )

        self.db.add(canvas)
        await self.db.commit()
        await self.db.refresh(canvas)

        logger.info(f"Canvas created: {canvas.id} by user {self.user_id}")
        return canvas

    async def get_canvas(self, canvas_id: UUID) -> Canvas:
        """Get canvas by ID with all related data."""
        result = await self.db.execute(
            select(Canvas).where(Canvas.id == canvas_id).where(Canvas.tenant_id == self.tenant_id)
        )
        canvas = result.scalar_one_or_none()

        if not canvas:
            raise NotFoundError(f"Canvas {canvas_id} not found")

        # Check access
        await self._check_canvas_access(canvas)

        return canvas

    async def list_canvases(
        self,
        search: str | None = None,
        template: str | None = None,
        owner_only: bool = False,
        shared_only: bool = False,
    ) -> list[Canvas]:
        """List canvases with filters."""
        query = select(Canvas).where(Canvas.tenant_id == self.tenant_id)

        # Owner filter
        if owner_only:
            query = query.where(Canvas.owner_id == self.user_id)

        # Search filter
        if search:
            query = query.where(Canvas.name.ilike(f"%{search}%"))

        # Template filter
        if template:
            query = query.where(Canvas.template == template)

        # Shared canvases (collaborator access)
        if shared_only:
            # This requires a join - simplified for now
            pass

        query = query.order_by(desc(Canvas.updated_at))

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_canvas(self, canvas_id: UUID, data: CanvasUpdate) -> Canvas:
        """Update canvas metadata."""
        canvas = await self.get_canvas(canvas_id)

        # Check edit permission
        await self._check_canvas_permission(canvas, required_role=CollaboratorRole.EDITOR)

        # Update fields
        if data.name is not None:
            canvas.name = data.name
        if data.is_public is not None:
            canvas.is_public = data.is_public

        canvas.version += 1
        await self.db.commit()
        await self.db.refresh(canvas)

        logger.info(f"Canvas updated: {canvas_id}")
        return canvas

    async def delete_canvas(self, canvas_id: UUID) -> None:
        """Delete canvas."""
        canvas = await self.get_canvas(canvas_id)

        # Only owner or admin can delete
        if canvas.owner_id != self.user_id:
            await self._check_canvas_permission(canvas, required_role=CollaboratorRole.ADMIN)

        await self.db.delete(canvas)
        await self.db.commit()

        logger.info(f"Canvas deleted: {canvas_id}")

    # =============================================================================
    # Block Operations
    # =============================================================================

    async def create_block(self, canvas_id: UUID, data: BlockCreate) -> CanvasBlock:
        """Create a new block on canvas."""
        canvas = await self.get_canvas(canvas_id)
        await self._check_canvas_permission(canvas, required_role=CollaboratorRole.EDITOR)

        block = CanvasBlock(
            canvas_id=canvas_id,
            type=data.type.value,
            x=data.position.x,
            y=data.position.y,
            width=data.size.width,
            height=data.size.height,
            z_index=data.z_index,
            content=data.content,
            agent_id=data.agent_id,
            execution_id=data.execution_id,
            created_by=self.user_id,
        )

        self.db.add(block)
        await self.db.commit()
        await self.db.refresh(block)

        # Track operation for OT
        await self._track_operation(
            canvas_id=canvas_id,
            operation_type="insert",
            target_type="block",
            target_id=block.id,
            data={
                "type": data.type.value,
                "position": {"x": float(data.position.x), "y": float(data.position.y)},
                "size": {"width": float(data.size.width), "height": float(data.size.height)},
            },
        )

        logger.info(f"Block created: {block.id} on canvas {canvas_id}")
        return block

    async def update_block(self, canvas_id: UUID, block_id: UUID, data: BlockUpdate) -> CanvasBlock:
        """Update a block."""
        canvas = await self.get_canvas(canvas_id)
        await self._check_canvas_permission(canvas, required_role=CollaboratorRole.EDITOR)

        result = await self.db.execute(
            select(CanvasBlock)
            .where(CanvasBlock.id == block_id)
            .where(CanvasBlock.canvas_id == canvas_id)
        )
        block = result.scalar_one_or_none()

        if not block:
            raise NotFoundError(f"Block {block_id} not found")

        # Track changes for OT
        changes: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        if data.position is not None:
            block.x = data.position.x
            block.y = data.position.y
            changes["position"] = {"x": float(data.position.x), "y": float(data.position.y)}

        if data.size is not None:
            block.width = data.size.width
            block.height = data.size.height
            changes["size"] = {"width": float(data.size.width), "height": float(data.size.height)}

        if data.z_index is not None:
            block.z_index = data.z_index
            changes["z_index"] = data.z_index

        if data.content is not None:
            block.content = data.content
            changes["content"] = data.content

        block.version += 1
        await self.db.commit()
        await self.db.refresh(block)

        # Track operation
        if changes:
            await self._track_operation(
                canvas_id=canvas_id,
                operation_type="update",
                target_type="block",
                target_id=block_id,
                data=changes,
            )

        logger.info(f"Block updated: {block_id}")
        return block

    async def delete_block(self, canvas_id: UUID, block_id: UUID) -> None:
        """Delete a block."""
        canvas = await self.get_canvas(canvas_id)
        await self._check_canvas_permission(canvas, required_role=CollaboratorRole.EDITOR)

        result = await self.db.execute(
            select(CanvasBlock)
            .where(CanvasBlock.id == block_id)
            .where(CanvasBlock.canvas_id == canvas_id)
        )
        block = result.scalar_one_or_none()

        if not block:
            raise NotFoundError(f"Block {block_id} not found")

        await self.db.delete(block)
        await self.db.commit()

        # Track operation
        await self._track_operation(
            canvas_id=canvas_id,
            operation_type="delete",
            target_type="block",
            target_id=block_id,
            data={},
        )

        logger.info(f"Block deleted: {block_id}")

    # =============================================================================
    # Connection Operations
    # =============================================================================

    async def create_connection(self, canvas_id: UUID, data: ConnectionCreate) -> CanvasConnection:
        """Create a connection between blocks."""
        canvas = await self.get_canvas(canvas_id)
        await self._check_canvas_permission(canvas, required_role=CollaboratorRole.EDITOR)

        connection = CanvasConnection(
            canvas_id=canvas_id,
            from_block_id=data.from_block_id,
            to_block_id=data.to_block_id,
            connection_type=data.connection_type,
            color=data.color,
            label=data.label,
            is_bidirectional=data.is_bidirectional,
            trigger=data.trigger,
        )

        self.db.add(connection)
        await self.db.commit()
        await self.db.refresh(connection)

        logger.info(f"Connection created: {connection.id}")
        return connection

    async def delete_connection(self, canvas_id: UUID, connection_id: UUID) -> None:
        """Delete a connection."""
        canvas = await self.get_canvas(canvas_id)
        await self._check_canvas_permission(canvas, required_role=CollaboratorRole.EDITOR)

        result = await self.db.execute(
            select(CanvasConnection)
            .where(CanvasConnection.id == connection_id)
            .where(CanvasConnection.canvas_id == canvas_id)
        )
        connection = result.scalar_one_or_none()

        if not connection:
            raise NotFoundError(f"Connection {connection_id} not found")

        await self.db.delete(connection)
        await self.db.commit()

        logger.info(f"Connection deleted: {connection_id}")

    # =============================================================================
    # Collaboration
    # =============================================================================

    async def add_collaborator(
        self, canvas_id: UUID, data: CollaboratorCreate
    ) -> CanvasCollaborator:
        """Add a collaborator to canvas."""
        canvas = await self.get_canvas(canvas_id)

        # Only owner or admin can add collaborators
        await self._check_canvas_permission(canvas, required_role=CollaboratorRole.ADMIN)

        collaborator = CanvasCollaborator(
            canvas_id=canvas_id,
            user_id=data.user_id,
            role=data.role.value,
            added_by=self.user_id,
        )

        self.db.add(collaborator)
        await self.db.commit()
        await self.db.refresh(collaborator)

        logger.info(f"Collaborator added: {data.user_id} to canvas {canvas_id}")
        return collaborator

    async def remove_collaborator(self, canvas_id: UUID, user_id: UUID) -> None:
        """Remove a collaborator from canvas."""
        canvas = await self.get_canvas(canvas_id)
        await self._check_canvas_permission(canvas, required_role=CollaboratorRole.ADMIN)

        result = await self.db.execute(
            select(CanvasCollaborator)
            .where(CanvasCollaborator.canvas_id == canvas_id)
            .where(CanvasCollaborator.user_id == user_id)
        )
        collaborator = result.scalar_one_or_none()

        if collaborator:
            await self.db.delete(collaborator)
            await self.db.commit()

            logger.info(f"Collaborator removed: {user_id} from canvas {canvas_id}")

    # =============================================================================
    # Helper Methods
    # =============================================================================

    async def _check_canvas_access(self, canvas: Canvas) -> None:
        """Check if user has any access to canvas."""
        # Owner always has access
        if canvas.owner_id == self.user_id:
            return

        # Public canvas
        if canvas.is_public:
            return

        # Check collaborator access
        result = await self.db.execute(
            select(CanvasCollaborator)
            .where(CanvasCollaborator.canvas_id == canvas.id)
            .where(CanvasCollaborator.user_id == self.user_id)
        )
        if result.scalar_one_or_none():
            return

        raise PermissionDeniedError(
            permission="access",
            resource=f"canvas:{canvas.id}",
            user_id=str(self.user_id),
        )

    async def _check_canvas_permission(
        self, canvas: Canvas, required_role: CollaboratorRole
    ) -> None:
        """Check if user has required permission level."""
        # Owner has all permissions
        if canvas.owner_id == self.user_id:
            return

        # Check collaborator role
        result = await self.db.execute(
            select(CanvasCollaborator)
            .where(CanvasCollaborator.canvas_id == canvas.id)
            .where(CanvasCollaborator.user_id == self.user_id)
        )
        collaborator = result.scalar_one_or_none()

        if not collaborator:
            raise PermissionDeniedError(
                permission="access",
                resource=f"canvas:{canvas.id}",
                user_id=str(self.user_id),
            )

        # Role hierarchy - using string values from database
        role_levels: dict[str, int] = {
            CollaboratorRole.VIEWER.value: 1,
            CollaboratorRole.EDITOR.value: 2,
            CollaboratorRole.ADMIN.value: 3,
        }

        user_level = role_levels.get(collaborator.role, 0)
        required_level = role_levels.get(required_role.value, 0)

        if user_level < required_level:
            raise PermissionDeniedError(
                permission=required_role.value,
                resource=f"canvas:{canvas.id}",
                user_id=str(self.user_id),
            )

    async def _track_operation(
        self,
        canvas_id: UUID,
        operation_type: str,
        target_type: str,
        target_id: UUID | None,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        client_id: str = "server",
    ) -> None:
        """Track an operation for OT sync."""
        # Get next revision number
        result = await self.db.execute(
            select(func.max(CanvasOperation.revision)).where(CanvasOperation.canvas_id == canvas_id)
        )
        max_revision = result.scalar() or 0

        operation = CanvasOperation(
            canvas_id=canvas_id,
            operation_type=operation_type,
            target_type=target_type,
            target_id=target_id,
            data=data,
            client_id=client_id,
            revision=max_revision + 1,
        )

        self.db.add(operation)
        await self.db.commit()

    async def get_operations_since(self, canvas_id: UUID, revision: int) -> list[CanvasOperation]:
        """Get all operations since a specific revision."""
        result = await self.db.execute(
            select(CanvasOperation)
            .where(CanvasOperation.canvas_id == canvas_id)
            .where(CanvasOperation.revision > revision)
            .order_by(CanvasOperation.revision)
        )
        return list(result.scalars().all())
