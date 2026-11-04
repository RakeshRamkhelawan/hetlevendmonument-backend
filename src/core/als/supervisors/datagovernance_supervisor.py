from typing import Any, Dict

from src.core.als.infrastructure.signal_bus import Signal
from src.core.als.supervisors.base_supervisor import BaseSupervisor
from src.core.shared.interfaces import ExecutionResult, TaskData


class DataGovernanceSupervisor(BaseSupervisor):
    def __init__(self, agent_id: str, tenant_id: int, **kwargs: Any) -> None:
        super().__init__(
            agent_id=agent_id, tenant_id=tenant_id, department="data_governance", **kwargs
        )

    async def decompose_task(self, task: TaskData) -> list[TaskData]:
        return [task]

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return await self.execute(task)
