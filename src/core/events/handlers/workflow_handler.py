"""
Workflow Event Handler - Processes workflow events within the monolith.

Migrated from: services/workflow-engine/src/index.js
Handles workflow lifecycle events and task creation.
"""

import logging
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.als.enterprise.departments.department_orchestrator import Department
from src.core.database.session import get_db_session
from src.core.events.pubsub_manager import EventType, PubSubMessage, RedisPubSubManager

logger = logging.getLogger(__name__)


class WorkflowEventHandler:
    """
    Handles workflow-related events.

    Responsibilities:
    - Create tasks when workflow starts
    - Update workflow status
    - Trigger department routing for tasks
    - Handle workflow completion/failure
    """

    def __init__(self, pubsub_manager: RedisPubSubManager) -> None:
        self.pubsub = pubsub_manager
        self.logger = logger

    async def register_handlers(self) -> None:
        """Register all workflow event handlers."""
        await self.pubsub.subscribe(EventType.WORKFLOW_STARTED, self.on_workflow_started)
        await self.pubsub.subscribe(EventType.WORKFLOW_COMPLETED, self.on_workflow_completed)
        await self.pubsub.subscribe(EventType.WORKFLOW_FAILED, self.on_workflow_failed)
        await self.pubsub.subscribe(EventType.TASK_CREATED, self.on_task_created)

        self.logger.info("[OK] WorkflowEventHandler registered")

    async def on_workflow_started(self, message: PubSubMessage) -> None:
        """
        Handle workflow.started event.

        Creates initial tasks and routes them to appropriate departments.
        """
        try:
            workflow_id = cast(Optional[str], message.data.get("workflow_id"))
            workflow_type = message.data.get("workflow_type", "default")
            tenant_id = message.tenant_id

            if workflow_id is None:
                self.logger.error("Missing workflow_id in workflow.started event")
                return
            if tenant_id is None:
                self.logger.error("Missing tenant_id in workflow.started event")
                return

            self.logger.info(f"[STARTED] Workflow started: {workflow_id} (type: {workflow_type})")

            # Create tasks based on workflow type
            tasks = self._generate_tasks_for_workflow(workflow_type, message.data)

            async with cast(AbstractAsyncContextManager[AsyncSession], get_db_session()) as db:
                for task in tasks:
                    # Save task to database
                    await self._create_task(db, workflow_id, task, tenant_id)

                    # Publish task created event
                    # Cast department to Department enum for type safety
                    dept = cast(Department, task.get("department"))
                    await self.pubsub.publish(
                        event_type=EventType.TASK_CREATED,
                        data={
                            "task_id": task["id"],
                            "workflow_id": workflow_id,
                            "name": task["name"],
                            "department": dept.value if dept else Department.OPERATIONS.value,
                            "assignee": task.get("assignee"),
                        },
                        tenant_id=tenant_id,
                        source="workflow_handler",
                    )

            self.logger.info(f"[OK] Created {len(tasks)} tasks for workflow {workflow_id}")

        except Exception as e:
            self.logger.error(f"[ERROR] Failed to handle workflow.started: {e}")

    async def on_workflow_completed(self, message: PubSubMessage) -> None:
        """Handle workflow.completed event."""
        workflow_id = message.data.get("workflow_id")
        self.logger.info(f"[OK] Workflow completed: {workflow_id}")

        # Send completion notification
        await self.pubsub.publish(
            event_type=EventType.SYSTEM_ALERT,
            data={
                "level": "info",
                "message": f"Workflow {workflow_id} completed successfully",
                "workflow_id": workflow_id,
            },
            tenant_id=message.tenant_id,
            source="workflow_handler",
        )

    async def on_workflow_failed(self, message: PubSubMessage) -> None:
        """Handle workflow.failed event."""
        workflow_id = message.data.get("workflow_id")
        error = message.data.get("error", "Unknown error")

        self.logger.error(f"[ERROR] Workflow failed: {workflow_id} - {error}")

        # Send alert notification
        await self.pubsub.publish(
            event_type=EventType.SYSTEM_ALERT,
            data={
                "level": "error",
                "message": f"Workflow {workflow_id} failed: {error}",
                "workflow_id": workflow_id,
                "error": error,
            },
            tenant_id=message.tenant_id,
            source="workflow_handler",
        )

    async def on_task_created(self, message: PubSubMessage) -> None:
        """
        Handle task.created event.

        Routes task to appropriate department using the GunaRouter.
        """
        try:
            task_id = message.data.get("task_id")
            department_str = message.data.get("department")
            tenant_id = message.tenant_id

            self.logger.info(f"[TASK] Task created: {task_id} -> {department_str}")

            # Convert department string to enum
            if department_str is None:
                self.logger.warning("No department specified, defaulting to OPERATIONS")
                department = Department.OPERATIONS
            else:
                try:
                    department = Department(cast(str, department_str))
                except ValueError:
                    self.logger.warning(
                        f"Unknown department: {department_str}, defaulting to OPERATIONS"
                    )
                    department = Department.OPERATIONS

            # Route to department (this will use the hybrid router)
            # Note: Actual routing happens in the agent system
            await self.pubsub.publish(
                event_type=EventType.AGENT_MESSAGE,
                data={
                    "action": "route_task",
                    "task_id": task_id,
                    "department": department.value,
                    "priority": message.data.get("priority", "medium"),
                },
                tenant_id=tenant_id,
                source="workflow_handler",
            )

        except Exception as e:
            self.logger.error(f"[ERROR] Failed to handle task.created: {e}")

    def _generate_tasks_for_workflow(
        self, workflow_type: str, workflow_data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate default tasks for a workflow type.

        This replaces the logic from workflow-engine/src/index.js
        """
        base_tasks: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        if workflow_type == "campaign":
            base_tasks = [
                {
                    "id": f"task_{self._generate_id()}",
                    "name": "Design brief maken",
                    "department": Department.PRODUCT_INNOVATION,
                    "assignee": None,
                    "priority": "high",
                },
                {
                    "id": f"task_{self._generate_id()}",
                    "name": "Copy schrijven",
                    "department": Department.SALES_MARKETING,
                    "assignee": None,
                    "priority": "medium",
                },
                {
                    "id": f"task_{self._generate_id()}",
                    "name": "Budget goedkeuring",
                    "department": Department.FINANCE,
                    "assignee": None,
                    "priority": "high",
                },
            ]
        elif workflow_type == "hiring":
            base_tasks = [
                {
                    "id": f"task_{self._generate_id()}",
                    "name": "Vacaturetekst schrijven",
                    "department": Department.HR,
                    "assignee": None,
                    "priority": "high",
                },
                {
                    "id": f"task_{self._generate_id()}",
                    "name": "CV screening",
                    "department": Department.HR,
                    "assignee": None,
                    "priority": "medium",
                },
            ]
        else:
            # Default workflow
            base_tasks = [
                {
                    "id": f"task_{self._generate_id()}",
                    "name": "Initial review",
                    "department": Department.OPERATIONS,
                    "assignee": None,
                    "priority": "medium",
                }
            ]

        return base_tasks

    async def _create_task(
        self,
        db: AsyncSession,
        workflow_id: str | None,
        task: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: int | None,
    ) -> None:
        """Create task in database."""
        # Placeholder - actual implementation would insert into tasks table
        # This would typically use SQLAlchemy models
        self.logger.debug(f"Creating task {task['id']} for workflow {workflow_id}")
        # Implementation depends on your Task model
        pass

    def _generate_id(self) -> str:
        """Generate unique ID."""
        import uuid

        return str(uuid.uuid4())[:8]
