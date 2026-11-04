"""Adapter: MasterOrchestratorAgent -> IAgentRuntime facade (ADR-034)."""

import logging
from typing import cast

from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent
from src.core.shared.interfaces import ExecutionResult, TaskData

logger = logging.getLogger(__name__)


class MasterOrchestratorRuntimeAdapter:
    """Wraps MasterOrchestratorAgent to implement IAgentRuntime protocol."""

    def __init__(self, orchestrator: MasterOrchestratorAgent) -> None:
        self._orchestrator = orchestrator

    async def orchestrate(self, task: TaskData) -> ExecutionResult:
        """Delegate complex multi-step workflows to MasterOrchestratorAgent."""
        return cast(ExecutionResult, await self._orchestrator.process_task(task))

    async def route(self, task: TaskData) -> ExecutionResult:
        """Route single tasks; delegates to orchestrator until AgentRouterAgent is wired."""
        # TODO(Rakesh): wire AgentRouterAgent directly for single-task routing (#SP-AGT-002)
        return cast(ExecutionResult, await self._orchestrator.process_task(task))

    async def get_health(self) -> dict[str, object]:
        """Return current health status of the agent system."""
        caps = await self._orchestrator.get_capabilities()
        llm_ready: bool = getattr(self._orchestrator, "llm_client", None) is not None
        return {
            "status": "healthy" if llm_ready else "degraded",
            "agent": type(self._orchestrator).__name__,
            "capabilities": len(caps),
            "llm_ready": llm_ready,
        }
