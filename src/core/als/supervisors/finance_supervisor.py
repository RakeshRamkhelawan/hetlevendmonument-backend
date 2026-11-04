import re
from typing import Any

from src.core.als.infrastructure.signal_bus import Signal
from src.core.als.supervisors.base_supervisor import BaseSupervisor
from src.core.exceptions import AuthError
from src.core.shared.interfaces import ExecutionResult, TaskData


class FinanceSupervisor(BaseSupervisor):
    """
    Domain supervisor for Finance & Treasury.
    Coordinates agents like tax_compliance, audit, and forecasting.
    """

    supervisor_id = "finance.treasury.supervisor"
    domain = "Finance & Treasury"
    managed_agents = [
        "finance.tax_compliance.001",
        "finance.audit_compliance.001",
        "finance.ar_ap.001",
        "finance.forecasting.001",
        "finance.investment.001",
    ]

    def __init__(
        self,
        agent_id: str = supervisor_id,
        tenant_id: int = 1,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            agent_id=agent_id, tenant_id=tenant_id, department="finance_treasury", **kwargs
        )
        self.supervisor_id = agent_id
        self.domain = self.__class__.domain
        self.managed_agents = list(self.__class__.managed_agents)

    @staticmethod
    def _require_tenant_id(tenant_id: object) -> str:
        if tenant_id is None:
            raise AuthError("tenant_id is required")
        if not isinstance(tenant_id, str):
            raise AuthError("tenant_id must be a string")

        if not tenant_id:
            raise AuthError("tenant_id is required")

        if len(tenant_id) > 128:
            raise AuthError("tenant_id too long")

        if re.match(r"^[a-zA-Z0-9_-]+$", tenant_id) is None:
            raise AuthError("tenant_id contains invalid characters")

        return tenant_id

    async def decompose_task(self, task: TaskData) -> list[TaskData]:
        """
        Financiele taak decompositie logica.
        Bijv: Een 'jaarverslag' wordt opgedeeld in 'audit' en 'tax' sub-taken.
        """
        task_payload = task.model_dump() if hasattr(task, "model_dump") else dict(task)
        tenant_id = self._require_tenant_id(task_payload.get("tenant_id"))
        metadata = task_payload.get("metadata") or {}
        task_type = task_payload.get("type") or metadata.get("type")
        title = str(task_payload.get("title", "")).lower()

        if task_type in {"tax_filing", "tax"} or "tax" in title:
            return [
                TaskData(
                    title="prepare_tax_filing",
                    description="Tax filing sub-task",
                    agent_id="finance.tax_compliance.001",
                    tenant_id=tenant_id if isinstance(tenant_id, int) else None,
                    metadata={**task_payload, "tenant_id": tenant_id},
                )
            ]

        if task_type in {"audit_review", "audit"} or "audit" in title:
            return [
                TaskData(
                    title="perform_audit_review",
                    description="Audit review sub-task",
                    agent_id="finance.audit_compliance.001",
                    tenant_id=tenant_id if isinstance(tenant_id, int) else None,
                    metadata={**task_payload, "tenant_id": tenant_id},
                )
            ]

        return []

    async def delegate(
        self,
        sub_tasks: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
        tenant_id: Any = None,  # TODO(TYPE): replace with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        resolved_tenant_id = self._require_tenant_id(tenant_id)
        if not sub_tasks:
            return {"status": "completed", "results": []}

        results = [
            {
                "agent_id": subtask.get("agent_id"),
                "task": subtask.get("task"),
                "tenant_id": resolved_tenant_id,
                "status": "completed",
            }
            for subtask in sub_tasks
        ]
        return {"status": "completed", "results": results}

    async def handle_timeout(
        self, agent_id: str, task: Any, tenant_id: Any = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        resolved_tenant_id = self._require_tenant_id(tenant_id)
        return {
            "status": "escalated",
            "agent_id": agent_id,
            "task": task,
            "tenant_id": resolved_tenant_id,
            "escalated_to": "cva.meta.supervisor",
        }
    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return await self.execute(task)
