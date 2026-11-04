from typing import Any, Dict, List

from src.core.als.infrastructure.signal_bus import Signal
from src.core.als.supervisors.base_supervisor import BaseSupervisor
from src.core.shared.interfaces import ExecutionResult, TaskData


class SalesMarketingSupervisor(BaseSupervisor):
    def __init__(self, agent_id: str, tenant_id: int, **kwargs: Any) -> None:
        super().__init__(
            agent_id=agent_id, tenant_id=tenant_id, department="sales_marketing", **kwargs
        )

    async def decompose_task(self, task: TaskData) -> list[TaskData]:
        return [task]

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return await self.execute(task)
