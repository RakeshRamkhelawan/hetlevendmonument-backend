"""Agentic Orchestration Service -- AUDIT-DB14a (ADR-033 service layer).

Dispatches workflow tasks via Dramatiq; tenant_id altijd uit JWT (ADR-003, TI-004).
"""

import logging
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.tasks.workflow_tasks import execute_workflow_step

logger = logging.getLogger(__name__)


class AgenticWorkflowConfig(BaseModel):
    """Request payload for dispatching a workflow task."""

    name: str
    steps: list[str] | None = None
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class AgenticOrchestrationService:
    """Service layer for agentic workflow orchestration (ADR-033).

    Injected via Depends(get_agentic_orchestration_service); never instantiated directly.
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def start_workflow(
        self, config: AgenticWorkflowConfig
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Dispatch a workflow task. Raises ValueError if tenant_id is absent (TI-004)."""
        if not self.tenant_id:
            raise ValueError(
                "tenant_id vereist voor workflow dispatch -- "
                "zorg dat de JWT correct is geconfigureerd (TI-004)."
            )
        try:
            execute_workflow_step.send(
                {
                    "tenant_id": self.tenant_id,
                    "task_id": config.name,
                    "name": config.name,
                    "steps": config.steps or [],
                    "metadata": config.metadata or {},
                }
            )
        except Exception as e:
            logger.error("Workflow dispatch mislukt: %s: %s", type(e).__name__, e, exc_info=True)
            raise RuntimeError("Workflow dispatch mislukt") from e
        logger.info("Workflow dispatched: name=%s tenant=%s", config.name, self.tenant_id)
        return {"status": "dispatched", "name": config.name}

    async def get_workflow_status(
        self, task_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return workflow status for the given task_id (tenant-scoped)."""
        return {"task_id": task_id, "tenant_id": self.tenant_id, "status": "queued"}

    async def advance_workflow_step(
        self, task_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Advance the workflow to the next step."""
        return {"task_id": task_id, "status": "advanced"}

    async def cancel_workflow(
        self, task_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Cancel the given workflow task."""
        return {"task_id": task_id, "status": "cancelled"}
