"""Legacy compatibility tenant service for generated agency e2e tests."""

from __future__ import annotations

import time
from typing import Any, Dict

from src.core.agents.generated import (
    agency_backend_architect,
    agency_brand_guardian,
    agency_content_creator,
    agency_frontend_developer,
    agency_growth_hacker,
    agency_security_engineer,
    agency_ui_designer,
)
from src.core.agents.llm_types import TaskData


class TenantAgentService:
    """Simple compatibility layer to execute legacy agency tasks by tenant."""

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        self._agents = {
            "ui_designer": agency_ui_designer,
            "security_engineer": agency_security_engineer,
            "backend_architect": agency_backend_architect,
            "growth_hacker": agency_growth_hacker,
            "content_creator": agency_content_creator,
            "frontend_developer": agency_frontend_developer,
            "brand_guardian": agency_brand_guardian,
        }

    async def execute(
        self,
        agent_name: str,
        task_type: str,
        payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        user_id: str,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        start = time.time()
        agent = self._agents.get(agent_name)
        if agent is None:
            return {
                "success": False,
                "error": f"Unknown agent: {agent_name}",
                "execution_time": time.time() - start,
            }

        await agent.initialize()

        task = TaskData(
            title=task_type,
            description=f"Legacy agency task: {task_type}",
        )

        result = await agent.process_task(task)
        return {
            "success": result.success,
            "result": result.result_data or {},
            "error": result.error_message,
            "execution_time": result.execution_time,
        }
