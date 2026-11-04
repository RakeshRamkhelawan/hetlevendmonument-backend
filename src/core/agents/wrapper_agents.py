"""
Wrapper agents for non-EnhancedBaseAgent agents.

These wrappers provide CriticAgent integration (SILENT mode) for agents
that don't inherit from EnhancedBaseAgent and therefore can't use CriticMixin.

Pattern: Wrapper delegates to wrapped agent, then pipes ExecutionResult
through CriticAgent for telemetry.
"""

import logging
from typing import Any, List, Optional, cast

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.mixins.critic_mixin import CriticMixin, CriticMode
from src.core.shared.interfaces import AgentCapability, ExecutionResult, TaskData
from src.core.types import AgentType

logger = logging.getLogger(__name__)


class AgentWrapper(CriticMixin, EnhancedBaseAgent):
    """
    Base wrapper for non-EnhancedBaseAgent agents.

    Usage:
        wrapped = SomeLegacyAgent()  # Doesn't extend EnhancedBaseAgent
        wrapper = AgentWrapper(wrapped_agent=wrapped, tenant_id=1)
        result = await wrapper.process_task(task)  # Wrapped + critiqued
    """

    def __init__(
        self,
        wrapped_agent: Any,  # TODO(TYPE): replace Any with concrete type
        agent_id: str | None = None,
        tenant_id: int = 1,
    ) -> None:
        _validate_tenant_id(tenant_id)
        # Generate agent_id from wrapped agent if not provided
        if agent_id is None:
            agent_id = f"wrapper_{wrapped_agent.__class__.__name__.lower()}_001"

        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.GENERIC,
            tenant_id=tenant_id,
        )

        # SILENT mode - only telemetry, no blocking
        self.__init_critic__(mode=CriticMode.SILENT)

        self.wrapped_agent = wrapped_agent
        self.wrapped_class_name = wrapped_agent.__class__.__name__

        logger.debug("AgentWrapper created for %s (tenant=%d)", self.wrapped_class_name, tenant_id)

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """
        Execute task via wrapped agent, then critique the result.
        """
        # Execute via wrapped agent
        if hasattr(self.wrapped_agent, "process_task"):
            result = await self.wrapped_agent.process_task(task)
        elif hasattr(self.wrapped_agent, "execute"):
            result = await self.wrapped_agent.execute(task)
        else:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                result_data={
                    "error": f"Wrapped agent {self.wrapped_class_name} has no execute method"
                },
                execution_time=0.0,
            )

        # Post-process through critic (SILENT mode - async, non-blocking)
        result = await self.post_process_task(result, task.id)

        return result

    async def get_capabilities(self) -> list[AgentCapability]:
        """Delegate to wrapped agent if possible."""
        if hasattr(self.wrapped_agent, "get_capabilities"):
            return cast(list[AgentCapability], await self.wrapped_agent.get_capabilities())
        return []


# --- Pre-configured wrappers for the 12 problematic agents -------------------


class AnalyzerAgentWrapper(AgentWrapper):
    """Wrapper for AnalyzerAgent."""

    def __init__(self, tenant_id: int = 1) -> None:
        _validate_tenant_id(tenant_id)
        from src.core.agents.analyzer_agent import AnalyzerAgent

        wrapped = AnalyzerAgent(tenant_id=tenant_id)
        super().__init__(wrapped, agent_id="analyzer_agent_wrapped_001", tenant_id=tenant_id)


class AutonomousAgentWrapper(AgentWrapper):
    """Wrapper for AutonomousAgent."""

    def __init__(self, tenant_id: int = 1) -> None:
        _validate_tenant_id(tenant_id)
        from src.core.agents.autonomous_agent import AutonomousAgent

        wrapped = AutonomousAgent()
        super().__init__(wrapped, agent_id="autonomous_agent_wrapped_001", tenant_id=tenant_id)


class CorrectiveRAGAgentWrapper(AgentWrapper):
    """Wrapper for CorrectiveRAGAgent."""

    def __init__(self, tenant_id: int = 1) -> None:
        _validate_tenant_id(tenant_id)
        from src.core.agents.corrective_rag_agent import CorrectiveRAGAgent

        wrapped = CorrectiveRAGAgent()
        super().__init__(wrapped, agent_id="corrective_rag_agent_wrapped_001", tenant_id=tenant_id)


class CVAAgentWrapper(AgentWrapper):
    """Wrapper for CVAAgent."""

    def __init__(self, tenant_id: int = 1) -> None:
        _validate_tenant_id(tenant_id)
        from src.core.agents.cva_agent import CVAAgent

        wrapped = CVAAgent(tenant_id=tenant_id)
        super().__init__(wrapped, agent_id="cva_agent_wrapped_001", tenant_id=tenant_id)


class ExecutionFeedbackAgentWrapper(AgentWrapper):
    """Wrapper for ExecutionFeedbackAgent."""

    def __init__(self, tenant_id: int = 1) -> None:
        _validate_tenant_id(tenant_id)
        from src.core.agents.execution_feedback_agent import ExecutionFeedbackAgent

        wrapped = ExecutionFeedbackAgent(tenant_id=tenant_id)
        super().__init__(
            wrapped, agent_id="execution_feedback_agent_wrapped_001", tenant_id=tenant_id
        )


class UltimateCVAAgentWrapper(AgentWrapper):
    """Wrapper for UltimateCVAAgent."""

    def __init__(self, tenant_id: int = 1) -> None:
        _validate_tenant_id(tenant_id)
        from src.core.agents.cva_orchestrator import UltimateCVAAgent

        wrapped = UltimateCVAAgent(tenant_id=tenant_id)
        super().__init__(wrapped, agent_id="cva_orchestrator_wrapped_001", tenant_id=tenant_id)


class WorkflowOrchestratorAgentWrapper(AgentWrapper):
    """Wrapper for WorkflowOrchestratorAgent."""

    def __init__(self, tenant_id: int = 1) -> None:
        _validate_tenant_id(tenant_id)
        from src.core.agents.workflow_orchestrator_agent import WorkflowOrchestratorAgent

        wrapped = WorkflowOrchestratorAgent(tenant_id=tenant_id, user_id=0)
        super().__init__(
            wrapped, agent_id="workflow_orchestrator_agent_wrapped_001", tenant_id=tenant_id
        )


class AgencyBackendArchitectAgentWrapper(AgentWrapper):
    """Wrapper for AgencyBackendArchitectAgent."""

    def __init__(self, tenant_id: int = 1) -> None:
        _validate_tenant_id(tenant_id)
        from src.core.agents.generated.agency_backend_architect_agent import (
            AgencyBackendArchitectAgent,
        )

        wrapped = AgencyBackendArchitectAgent()
        super().__init__(
            wrapped, agent_id="agency_backend_architect_agent_wrapped_001", tenant_id=tenant_id
        )


class AgencyFrontendDeveloperAgentWrapper(AgentWrapper):
    """Wrapper for AgencyFrontendDeveloperAgent."""

    def __init__(self, tenant_id: int = 1) -> None:
        _validate_tenant_id(tenant_id)
        from src.core.agents.generated.agency_frontend_developer_agent import (
            AgencyFrontendDeveloperAgent,
        )

        wrapped = AgencyFrontendDeveloperAgent()
        super().__init__(
            wrapped, agent_id="agency_frontend_developer_agent_wrapped_001", tenant_id=tenant_id
        )


class AgencyGrowthHackerAgentWrapper(AgentWrapper):
    """Wrapper for AgencyGrowthHackerAgent."""

    def __init__(self, tenant_id: int = 1) -> None:
        _validate_tenant_id(tenant_id)
        from src.core.agents.generated.agency_growth_hacker_agent import AgencyGrowthHackerAgent

        wrapped = AgencyGrowthHackerAgent()
        super().__init__(
            wrapped, agent_id="agency_growth_hacker_agent_wrapped_001", tenant_id=tenant_id
        )


class AgencySecurityEngineerAgentWrapper(AgentWrapper):
    """Wrapper for AgencySecurityEngineerAgent."""

    def __init__(self, tenant_id: int = 1) -> None:
        _validate_tenant_id(tenant_id)
        from src.core.agents.generated.agency_security_engineer_agent import (
            AgencySecurityEngineerAgent,
        )

        wrapped = AgencySecurityEngineerAgent()
        super().__init__(
            wrapped, agent_id="agency_security_engineer_agent_wrapped_001", tenant_id=tenant_id
        )


class AgencyUIDesignerAgentWrapper(AgentWrapper):
    """Wrapper for AgencyUIDesignerAgent."""

    def __init__(self, tenant_id: int = 1) -> None:
        _validate_tenant_id(tenant_id)
        from src.core.agents.generated.agency_ui_designer_agent import AgencyUiDesignerAgent

        wrapped = AgencyUiDesignerAgent()
        super().__init__(
            wrapped, agent_id="agency_ui_designer_agent_wrapped_001", tenant_id=tenant_id
        )


# --- Factory function -------------------------------------------------------

WRAPPER_MAP = {
    "AnalyzerAgent": AnalyzerAgentWrapper,
    "AutonomousAgent": AutonomousAgentWrapper,
    "CorrectiveRAGAgent": CorrectiveRAGAgentWrapper,
    "CVAAgent": CVAAgentWrapper,
    "ExecutionFeedbackAgent": ExecutionFeedbackAgentWrapper,
    "UltimateCVAAgent": UltimateCVAAgentWrapper,
    "WorkflowOrchestratorAgent": WorkflowOrchestratorAgentWrapper,
    "AgencyBackendArchitectAgent": AgencyBackendArchitectAgentWrapper,
    "AgencyFrontendDeveloperAgent": AgencyFrontendDeveloperAgentWrapper,
    "AgencyGrowthHackerAgent": AgencyGrowthHackerAgentWrapper,
    "AgencySecurityEngineerAgent": AgencySecurityEngineerAgentWrapper,
    "AgencyUIDesignerAgent": AgencyUIDesignerAgentWrapper,
}


def _validate_tenant_id(tenant_id: int) -> None:
    """Fail closed on invalid tenant input before any wrapper construction."""
    if not isinstance(tenant_id, int) or tenant_id <= 0:
        raise ValueError("tenant_id must be a positive integer")


def get_wrapped_agent(agent_class_name: str, tenant_id: int = 1) -> AgentWrapper | None:
    """
    Get a wrapped version of an agent that doesn't extend EnhancedBaseAgent.

    Args:
        agent_class_name: Name of the agent class to wrap
        tenant_id: Tenant ID

    Returns:
        AgentWrapper instance or None if not found
    """
    _validate_tenant_id(tenant_id)
    # WorkflowOrchestratorAgent requires user_id context not available via this factory.
    # Fail closed: callers must construct WorkflowOrchestratorAgentWrapper directly with user_id.
    if agent_class_name == "WorkflowOrchestratorAgent":
        return None
    wrapper_class = WRAPPER_MAP.get(agent_class_name)
    if wrapper_class:
        return wrapper_class(tenant_id)
    return None


def list_wrappable_agents() -> list[str]:
    """List all agent types that can be wrapped."""
    return list(WRAPPER_MAP.keys())
