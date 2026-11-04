from typing import Any, Dict, List

from src.core.als.infrastructure.signal_bus import Signal
from src.core.als.supervisors.base_supervisor import BaseSupervisor
from src.core.shared.interfaces import ExecutionResult, TaskData


class CVASupervisor(BaseSupervisor):
    """
    The Ultimate Meta-Supervisor (CEO level).
    Orchestrates across all 10 departments.
    """

    def __init__(self, agent_id: str, tenant_id: int, **kwargs: Any) -> None:
        super().__init__(agent_id=agent_id, tenant_id=tenant_id, department="meta", **kwargs)

    async def decompose_task(self, task: TaskData) -> list[TaskData]:
        """Cross-department task decomposition."""
        return [task]

    async def select_agents(self, sub_tasks: list[TaskData]) -> list[str]:
        """
        CVA can select ANY supervisor or agent across the entire organization.
        """
        selected: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Access through metadata as per TaskData interface
        content = str(sub_tasks[0].metadata).lower() + " " + sub_tasks[0].description.lower()

        if "tax" in content or "finance" in content:
            selected.append("finance_supervisor")
        elif "hire" in content or "hr" in content:
            selected.append("hr_supervisor")

        return selected

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return await self.execute(task)
