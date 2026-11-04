"""
Workflow Domain Services - FASE 1.2 DDD
"""

from typing import Any

from loguru import logger

from src.core.agents.router_agent_service import RouterAgentService
from src.core.governance.audit import AuditService
from src.core.utils.best_effort import best_effort
from .models import Workflow, WorkflowStatus, WorkflowStep


class WorkflowService:
    """
    Workflow Domain Service
    Orchestrates workflow execution
    """

    def __init__(
        self,
        router: RouterAgentService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._router = router
        self._audit_service = audit_service

    async def create_workflow(
        self,
        name: str,
        tenant_id: str,
        steps: list[Any],  # TODO(TYPE): replace Any with concrete type
    ) -> Workflow:  # TODO(TYPE): replace Any with concrete type
        """Create new workflow"""
        workflow = Workflow(
            id=self._generate_workflow_id(),
            name=name,
            tenant_id=tenant_id,
            status=WorkflowStatus.PENDING,
        )

        # Add steps
        for idx, step_config in enumerate(steps):
            step = WorkflowStep(
                id=f"{workflow.id}_step_{idx}",
                name=step_config["name"],
                step_type=step_config["type"],
                config=step_config.get("config", {}),
                order=idx,
                dependencies=step_config.get("dependencies", []),
            )
            workflow.add_step(step)

        workflow.add_domain_event(
            {
                "type": "workflow.created",
                "aggregate_id": workflow.id,
                "data": {
                    "workflow_id": workflow.id,
                    "name": name,
                    "tenant_id": tenant_id,
                    "steps_count": len(steps),
                },
            }
        )

        return workflow

    async def execute_workflow(
        self, workflow: Workflow
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute workflow steps"""
        workflow.start()

        try:
            results: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
            for step in sorted(workflow.steps, key=lambda s: s.order):
                step_result = await self._execute_step(step, workflow.tenant_id)
                results.append(step_result)

            if any(r.get("status") in ("not_implemented", "skipped", "failed") for r in results):
                workflow.fail("One or more steps did not complete successfully")
                async with best_effort("workflow failed audit"):
                    if self._audit_service is not None:
                        await self._audit_service.log_action(
                            tenant_id=workflow.tenant_id,  # type: ignore[arg-type]
                            action="WORKFLOW_FAILED",
                            resource=f"workflow:{workflow.id}",
                            details={"status": "failed"},
                        )
                return {"status": "failed", "error": "Step execution incomplete"}

            workflow.complete({"steps_results": results})
            async with best_effort("workflow completed audit"):
                if self._audit_service is not None:
                    await self._audit_service.log_action(
                        tenant_id=workflow.tenant_id,  # type: ignore[arg-type]
                        action="WORKFLOW_EXECUTED",
                        resource=f"workflow:{workflow.id}",
                        details={"status": "completed", "steps_count": len(results)},
                    )
            return {"status": "completed", "results": results}
        except Exception as e:
            error_code = f"{type(e).__name__}_ERROR"
            workflow.fail(error_code)
            async with best_effort("workflow exception audit"):
                if self._audit_service is not None:
                    await self._audit_service.log_action(
                        tenant_id=workflow.tenant_id,  # type: ignore[arg-type]
                        action="WORKFLOW_FAILED",
                        resource=f"workflow:{workflow.id}",
                        details={"status": "failed", "error_code": error_code},
                    )
            return {"status": "failed", "error_code": error_code}

    async def _execute_step(
        self, step: WorkflowStep, tenant_id: str | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute individual workflow step via RouterAgentService."""
        if self._router is None:
            logger.bind(step_id=step.id, step_name=step.name).warning(
                "WorkflowService._execute_step: no router configured -- step skipped"
            )
            return {"step_id": step.id, "step_name": step.name, "status": "skipped"}

        query = step.config.get("description", step.name)
        try:
            result = await self._router.execute_request(query, tenant_id=tenant_id)
            return {
                "step_id": step.id,
                "step_name": step.name,
                "status": "completed",
                "output": result,
            }
        except Exception as exc:
            error_code = f"{type(exc).__name__}_ERROR"
            logger.opt(exception=True).error(
                "WorkflowService._execute_step failed with code: {}", error_code
            )
            return {
                "step_id": step.id,
                "step_name": step.name,
                "status": "failed",
                "error_code": error_code,
            }

    def _generate_workflow_id(self) -> str:
        """Generate unique workflow ID"""
        import uuid

        return f"wf_{uuid.uuid4().hex[:12]}"
