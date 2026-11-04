"""
Repository layer for ProcedureExecution model
Handles all database operations for procedure executions with audit trail
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ProcedureExecution
from .schemas import ProcedureExecutionCreate, ProcedureExecutionStatusUpdate


class ProcedureExecutionRepository:
    """Repository for procedure execution database operations"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, tenant_id: UUID, data: ProcedureExecutionCreate) -> ProcedureExecution:
        """
        Create new procedure execution record

        Args:
            tenant_id: Current tenant ID
            data: ProcedureExecutionCreate schema

        Returns:
            Created ProcedureExecution model
        """
        execution = ProcedureExecution(
            tenant_id=tenant_id,
            procedure_id=data.procedure_id,
            input=data.input,
            status="pending_approval",
            audit_trail=[
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": "created",
                    "status": "pending_approval",
                    "message": "Execution record created",
                }
            ],
        )
        self.db.add(execution)
        await self.db.flush()
        await self.db.refresh(execution)
        return execution

    async def get_by_id(self, tenant_id: UUID, execution_id: UUID) -> ProcedureExecution | None:
        """
        Get procedure execution by ID with tenant filtering

        Args:
            tenant_id: Current tenant ID (for scoping)
            execution_id: Procedure execution ID

        Returns:
            ProcedureExecution if found and belongs to tenant, None otherwise
        """
        stmt = select(ProcedureExecution).where(
            and_(
                ProcedureExecution.id == execution_id,
                ProcedureExecution.tenant_id == tenant_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_procedure(
        self, tenant_id: UUID, procedure_id: UUID
    ) -> list[ProcedureExecution]:
        """
        List all executions for a procedure

        Args:
            tenant_id: Current tenant ID (for scoping)
            procedure_id: Procedure metadata ID to filter by

        Returns: List[Any] of ProcedureExecution objects  # TODO(TYPE): replace Any with concrete type
        """
        stmt = (
            select(ProcedureExecution)
            .where(
                and_(
                    ProcedureExecution.tenant_id == tenant_id,
                    ProcedureExecution.procedure_id == procedure_id,
                )
            )
            .order_by(ProcedureExecution.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_status(self, tenant_id: UUID, status: str) -> list[ProcedureExecution]:
        """
        List all executions with specific status

        Args:
            tenant_id: Current tenant ID
            status: Status to filter by (pending_approval, running, completed, failed, etc.)

        Returns: List[Any] of ProcedureExecution objects  # TODO(TYPE): replace Any with concrete type
        """
        stmt = (
            select(ProcedureExecution)
            .where(
                and_(
                    ProcedureExecution.tenant_id == tenant_id,
                    ProcedureExecution.status == status,
                )
            )
            .order_by(ProcedureExecution.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tenant(
        self, tenant_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[ProcedureExecution]:
        """
        List all executions for a tenant with pagination

        Args:
            tenant_id: Current tenant ID
            skip: Pagination offset
            limit: Max records

        Returns: List[Any] of ProcedureExecution objects  # TODO(TYPE): replace Any with concrete type
        """
        stmt = (
            select(ProcedureExecution)
            .where(ProcedureExecution.tenant_id == tenant_id)
            .order_by(ProcedureExecution.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self, tenant_id: UUID, execution_id: UUID, data: ProcedureExecutionStatusUpdate
    ) -> ProcedureExecution | None:
        """
        Update execution status and optionally set output

        Args:
            tenant_id: Current tenant ID (for scoping)
            execution_id: Execution ID to update
            data: Status update data

        Returns:
            Updated ProcedureExecution or None if not found
        """
        execution = await self.get_by_id(tenant_id, execution_id)
        if not execution:
            return None

        # Record audit trail entry
        old_status = execution.status
        execution.status = data.status

        if data.output is not None:
            execution.output = data.output
        if data.error_message is not None:
            execution.error_message = data.error_message

        # Add audit trail entry
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "status_updated",
            "from_status": old_status,
            "to_status": data.status,
            "error": data.error_message,
        }

        if not isinstance(execution.audit_trail, list):
            execution.audit_trail = []
        execution.audit_trail.append(audit_entry)

        # Update timestamps
        if data.status == "running" and execution.started_at is None:
            execution.started_at = datetime.now(timezone.utc)
        elif data.status in ["completed", "failed", "cancelled"] and execution.completed_at is None:
            execution.completed_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(execution)
        return execution

    async def append_audit_entry(
        self,
        tenant_id: UUID,
        execution_id: UUID,
        action: str,
        details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ProcedureExecution | None:
        """
        Append entry to audit trail without changing status

        Args:
            tenant_id: Current tenant ID (for scoping)
            execution_id: Execution ID
            action: Action description
            details: Additional details

        Returns:
            Updated ProcedureExecution or None if not found
        """
        execution = await self.get_by_id(tenant_id, execution_id)
        if not execution:
            return None

        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            **(details or {}),
        }

        if not isinstance(execution.audit_trail, list):
            execution.audit_trail = []
        execution.audit_trail.append(audit_entry)

        await self.db.flush()
        await self.db.refresh(execution)
        return execution

    async def get_count(self, tenant_id: UUID, status: str | None = None) -> int:
        """
        Get count of executions

        Args:
            tenant_id: Current tenant ID
            status: Optional status filter

        Returns:
            Count of matching executions
        """
        conditions = [ProcedureExecution.tenant_id == tenant_id]
        if status:
            conditions.append(ProcedureExecution.status == status)

        stmt = select(func.count()).select_from(ProcedureExecution).where(and_(*conditions))
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def commit(self) -> None:
        """Commit database transaction"""
        await self.db.commit()

    async def rollback(self) -> None:
        """Rollback database transaction"""
        await self.db.rollback()
