"""
Workflow Service Layer.
Encapsulates all database logic for Workflows, removing it from Router.
Enforces Strict Layering: Router -> Service -> Data Access
"""

import uuid
from typing import Any, Optional

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.exceptions import raise_not_found
from src.core.shared.events.governance_bus import governance_bus
from src.core.shared.events.governance_events import SecurityAuditEvent
from src.core.utils.best_effort import best_effort
from src.core.workflow.models import C7Workflow as Workflow
from src.core.workflow.models import C7WorkflowExecution as WorkflowExecution
from src.core.workflow.models import WorkflowStatus


class WorkflowService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_workflow(
        self,
        tenant_id: int,
        user_id: int,
        workflow_id: str,
        name: str,
        description: str,
        workflow_type: str,
        trigger_type: str,
        spec: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout: int,
        metadata: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> Workflow:
        """Create a new workflow or update existing one (safe, transactional).

        Since DB PK is on workflow_id only, we UPDATE existing workflows
        and increment the version field for tracking.
        """
        # Check existing
        query = select(Workflow).where(
            and_(Workflow.workflow_id == workflow_id, Workflow.tenant_id == tenant_id)
        )
        result = await self.db.execute(query)
        existing = result.scalars().first()

        # Extract nodes and edges from spec
        nodes = spec.get("nodes", spec.get("tasks", []))
        edges = spec.get("edges", spec.get("dependencies", {}))

        if existing:
            # UPDATE existing workflow (PK is workflow_id only)
            existing.version = (existing.version or 0) + 1
            existing.name = name
            existing.description = description
            existing.workflow_type = workflow_type
            existing.trigger_type = trigger_type
            existing.nodes = nodes
            existing.edges = edges
            existing.variables = metadata
            existing.is_active = True
            workflow = existing
        else:
            # CREATE new workflow
            workflow = Workflow(
                workflow_id=workflow_id,
                name=name,
                description=description,
                version=1,
                workflow_type=workflow_type,
                trigger_type=trigger_type,
                nodes=nodes,
                edges=edges,
                variables=metadata,
                tenant_id=tenant_id,
                owner_id=user_id,
                is_active=True,
            )
            self.db.add(workflow)

        await self.db.flush()
        await self.db.commit()

        # Audit Log
        async with best_effort("CREATE_WORKFLOW audit"):
            await governance_bus.emit(
                SecurityAuditEvent(
                    tenant_id=tenant_id,
                    event_type="CREATE_WORKFLOW",
                    action="CREATE_WORKFLOW",
                    entity_id=workflow_id,
                    details={
                        "workflow_id": workflow_id,
                        "version": workflow.version,
                        "name": name,
                    },
                    user_id=user_id,
                )
            )

        return workflow

    async def get_workflow(
        self, tenant_id: int, workflow_id: str, version: int | None = None
    ) -> Workflow | None:
        """Get workflow by ID and optional version"""
        query = select(Workflow).where(
            and_(Workflow.workflow_id == workflow_id, Workflow.tenant_id == tenant_id)
        )
        if version:
            query = query.where(Workflow.version == version)
        else:
            query = query.order_by(Workflow.version.desc())

        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_workflows(
        self, tenant_id: int, limit: int = 50, offset: int = 0
    ) -> list[Workflow]:
        """List active workflows"""
        query = (
            select(Workflow)
            .where(Workflow.tenant_id == tenant_id)
            .order_by(Workflow.version.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def delete_workflow(self, tenant_id: int, workflow_id: str, user_id: int) -> bool:
        """Soft delete workflow"""
        # Verify exists first
        if not await self.get_workflow(tenant_id, workflow_id):
            return False

        await self.db.execute(
            update(Workflow)
            .where(and_(Workflow.workflow_id == workflow_id, Workflow.tenant_id == tenant_id))
            .values(is_active=False)
        )
        await self.db.commit()

        # Audit Log
        async with best_effort("DELETE_WORKFLOW audit"):
            await governance_bus.emit(
                SecurityAuditEvent(
                    tenant_id=tenant_id,
                    event_type="DELETE_WORKFLOW",
                    action="DELETE_WORKFLOW",
                    entity_id=workflow_id,
                    details={"workflow_id": workflow_id},
                    user_id=user_id,
                )
            )
        return True

    async def create_execution(
        self,
        tenant_id: int,
        user_id: int,
        workflow_id: str,
        input_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        version: int | None = None,
    ) -> WorkflowExecution:
        """Create execution record"""
        # Find workflow
        workflow = await self.get_workflow(tenant_id, workflow_id, version)
        if not workflow or (not version and not workflow.is_active):
            # If no version specified, requires active. If version specified, can execute inactive (historical)
            raise_not_found("Workflow", workflow_id)

        # Defense in depth: mypy narrowing after raise_not_found
        assert workflow is not None

        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        execution = WorkflowExecution(
            id=execution_id,  # Primary key
            execution_id=execution_id,  # UUID for idempotency
            workflow_id=workflow.id,
            tenant_id=tenant_id,
            status=WorkflowStatus.PENDING,
            input_json=input_data,
            output_json={},
            tasks_completed=0,
            tasks_failed=0,
            tasks_total=len(workflow.nodes or []),  # Use nodes instead of spec_json
            initiated_by=str(user_id),
        )
        self.db.add(execution)
        await self.db.commit()
        return execution

    async def get_execution(self, tenant_id: int, execution_id: str) -> WorkflowExecution | None:
        """Get execution details"""
        query = select(WorkflowExecution).where(
            and_(
                WorkflowExecution.execution_id == execution_id,
                WorkflowExecution.tenant_id == tenant_id,
            )
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list_executions(
        self,
        tenant_id: int,
        workflow_id: str | None = None,
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowExecution]:
        """List executions"""
        query = (
            select(WorkflowExecution)
            .options(selectinload(WorkflowExecution.workflow))
            .where(WorkflowExecution.tenant_id == tenant_id)
        )

        if workflow_id:
            query = query.join(Workflow).where(Workflow.workflow_id == workflow_id)
        if status_filter:
            query = query.where(WorkflowExecution.status == status_filter)

        query = query.order_by(WorkflowExecution.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())
