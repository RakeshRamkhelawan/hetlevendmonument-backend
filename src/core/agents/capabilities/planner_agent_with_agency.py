"""
Planner Agent with Agency Capabilities Integration

This demonstrates the CORRECT way to integrate Agency skills:
- Not as standalone agents
- But as capabilities within existing SanskritiSetu agents
"""

from typing import Any, Dict, List, Optional

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.capabilities.agency_capabilities import AgencyCapabilityRegistry
from src.core.shared.interfaces import AgentCapability, AgentType, ExecutionResult, TaskData


class PlannerAgentWithAgency(EnhancedBaseAgent):
    """
    Planner Agent that includes Agency capabilities.

    This is the CORRECT integration pattern:
    - Inherits from EnhancedBaseAgent (existing base)
    - Uses existing AgentRegistry
    - Participates in workflow engine
    - Emits events via existing event bus
    - Uses Agency skills as specialized capabilities
    """

    def __init__(
        self, agent_id: str = "planner_with_agency_001", tenant_id: int = 1, **kwargs: Any
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.COORDINATOR,  # NOTE: PLANNER not in enum; COORDINATOR is closest
            tenant_id=tenant_id,
            **kwargs,
        )

    async def _initialize_capabilities(self) -> None:
        """
        Initialize capabilities including Agency skills.

        This is where Agency capabilities are integrated into
        the existing agent architecture.
        """
        self._capabilities = [
            # Standard planner capabilities
            AgentCapability(
                name="plan_procedure",
                description="Plan procedure execution",
                input_types=["procedure", "context"],
                output_types=["execution_plan"],
                resource_requirements={"memory": "128MB"},
            ),
            # AGENCY CAPABILITIES (integrated as skills)
            AgentCapability(
                name="agency_design_system",
                description="Generate design system (The Agency: UI Designer)",
                input_types=["design_requirements"],
                output_types=["design_system", "css_variables", "component_tokens"],
                resource_requirements={"memory": "256MB"},
            ),
            AgentCapability(
                name="agency_react_component",
                description="Generate React component (The Agency: Frontend Developer)",
                input_types=["component_spec"],
                output_types=["component_code", "tests"],
                resource_requirements={"memory": "128MB"},
            ),
            AgentCapability(
                name="agency_threat_model",
                description="Security threat modeling (The Agency: Security Engineer)",
                input_types=["system_description"],
                output_types=["threat_model", "mitigations"],
                resource_requirements={"memory": "256MB"},
            ),
            AgentCapability(
                name="agency_viral_loop",
                description="Design viral growth mechanics (The Agency: Growth Hacker)",
                input_types=["product_type"],
                output_types=["growth_strategy", "viral_mechanics"],
                resource_requirements={"memory": "128MB"},
            ),
        ]

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """
        Execute task, routing to appropriate capability.

        This handles both standard capabilities and Agency capabilities.
        """
        task_type = task.metadata.get("type", "")

        # Route Agency capabilities
        if task_type.startswith("agency_"):
            return await self._execute_agency_capability(task)

        # Handle standard capabilities
        if task_type == "plan_procedure":
            return await self._plan_procedure(task)

        return ExecutionResult(
            task_id=task.id,
            success=False,
            error_message=f"Unknown task type: {task_type}",
        )

    async def _execute_agency_capability(self, task: TaskData) -> ExecutionResult:
        """
        Execute an Agency capability.

        This integrates with the AgencyCapabilityRegistry to
        use The Agency skills within the existing agent flow.
        """
        import time

        start_time = time.time()

        task_type = task.metadata.get("type", "")

        try:
            # Get capability handler from registry
            handler = AgencyCapabilityRegistry.get(task_type)

            if not handler:
                return ExecutionResult(
                    task_id=task.id,
                    success=False,
                    error_message=f"Agency capability not found: {task_type}",
                    execution_time=time.time() - start_time,
                )

            # Execute the Agency skill
            result_data = handler(task.payload)

            # Emit event (integrated with existing event system)
            await self.emit_event(
                "agency_capability_executed",
                {
                    "agent_id": self.agent_id,
                    "capability": task_type,
                    "tenant_id": self.tenant_id,
                    "success": True,
                },
            )

            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data=result_data,
                execution_time=time.time() - start_time,
            )

        except Exception as e:
            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Agency capability failed: {str(e)}",
                execution_time=time.time() - start_time,
            )

    async def _plan_procedure(self, task: TaskData) -> ExecutionResult:
        """Standard procedure planning capability"""
        import time

        start_time = time.time()

        # Implementation here
        result = {
            "steps": ["step1", "step2", "step3"],
            "estimated_duration": "5m",
        }

        return ExecutionResult(
            task_id=task.id,
            success=True,
            result_data=result,
            execution_time=time.time() - start_time,
        )


# Factory function for creating planner with agency
def create_planner_agent_with_agency(tenant_id: int, **kwargs: Any) -> PlannerAgentWithAgency:
    """
    Factory function to create a planner agent with Agency capabilities.

    This is the entry point for creating an agent that has both
    standard planning capabilities AND Agency skills.

    Usage:
        >>> from src.core.agents.capabilities.planner_agent_with_agency import create_planner_agent_with_agency
        >>> agent = create_planner_agent_with_agency(tenant_id=847)
        >>> await agent.initialize()
        >>>
        >>> # Use Agency capability
        >>> task = TaskData(
        ...     id="task_001",
        ...     title="Design System",
        ...     payload={"brand_colors": {"primary": "#6366f1"}},
        ...     metadata={"type": "agency_design_system"},
        ... )
        >>> result = await agent.process_task(task)
    """
    return PlannerAgentWithAgency(
        agent_id=f"planner_agency_{tenant_id}", tenant_id=tenant_id, **kwargs
    )
