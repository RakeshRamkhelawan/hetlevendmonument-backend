"""
Workflow Domain Models - FASE 1.2 DDD
"""

from enum import Enum
from typing import Any, Optional

from pydantic import Field

from src.domains.shared import AggregateRoot


class WorkflowStatus(str, Enum):
    """Workflow execution status"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStep(AggregateRoot):
    """Individual step in a workflow"""

    name: str
    step_type: str
    config: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    order: int
    dependencies: list[str] = Field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PENDING
    result: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class Workflow(AggregateRoot):
    """
    Workflow Aggregate Root
    Represents an automated workflow process
    """

    name: str
    description: str | None = None
    tenant_id: str
    steps: list[WorkflowStep] = Field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PENDING
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    def start(self) -> None:
        """Start workflow execution"""
        if self.status != WorkflowStatus.PENDING:
            raise ValueError(f"Cannot start workflow in {self.status} state")

        self.status = WorkflowStatus.RUNNING
        self.add_domain_event(
            {
                "type": "workflow.started",
                "aggregate_id": self.id,
                "data": {
                    "workflow_id": self.id,
                    "name": self.name,
                    "tenant_id": self.tenant_id,
                },
            }
        )

    def complete(self, result: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Mark workflow as completed"""
        self.status = WorkflowStatus.COMPLETED
        self.metadata["result"] = result
        self.add_domain_event(
            {
                "type": "workflow.completed",
                "aggregate_id": self.id,
                "data": {"workflow_id": self.id, "result": result},
            }
        )

    def fail(self, error: str) -> None:
        """Mark workflow as failed"""
        self.status = WorkflowStatus.FAILED
        self.metadata["error"] = error
        self.add_domain_event(
            {
                "type": "workflow.failed",
                "aggregate_id": self.id,
                "data": {"workflow_id": self.id, "error": error},
            }
        )

    def add_step(self, step: WorkflowStep) -> None:
        """Add step to workflow"""
        self.steps.append(step)
