"""
Execution Path Adapters for Unified Gateway (Phase A3)

Adapters that WOULD wrap all 6 parallel execution paths to route through
UnifiedAgentGateway, if the gateway were instantiated anywhere.

STATUS (GOV-001, audit 2026-07-02): NOT WIRED INTO PRODUCTION EXECUTION PATHS.
`UnifiedAgentGateway` is defined and these adapters exist, but nothing in
base_agent.py, Dramatiq actors, or the orchestrators constructs a
`GatewayAdapterRegistry` or `UnifiedAgentGateway` instance. Governance is
instead enforced directly via `GovernanceContract.is_action_permitted()` on
each agent (see base_agent.py, autonomous_agent.py, chief_orchestrator.py).
Decision: keep this module (it has its own passing unit tests) but do not
claim it provides governance enforcement until it is actually instantiated
in a real execution path -- see tests/architecture/test_unified_agent_gateway_instantiated.py.

Path 1: EnhancedBaseAgent.process_task() - REST sync execution
Path 2: PerfectOrchestrator + SubagentManager - Orchestration execution
Path 3: CVA State Machine - Conversational Voice Agent
Path 4: Dramatiq Async Workflow - Background task execution
Path 5: SubAgent Factory (M-MDP) - Multi-MDP agent execution
Path 6: WebSocket LangGraph Stream - Real-time streaming execution
"""

import logging
from typing import Any, Optional
from collections.abc import Callable

from src.core.agents.unified_gateway import UnifiedAgentGateway
from src.core.shared.interfaces import ExecutionResult, TaskData

logger = logging.getLogger(__name__)


class ExecutionPathAdapter:
    """Base adapter for execution paths to the unified gateway."""

    def __init__(self, gateway: UnifiedAgentGateway, path_name: str):
        self.gateway = gateway
        self.path_name = path_name
        logger.info(f"[GATEWAY] Registered execution path adapter: {path_name}")

    async def execute(
        self, task: TaskData, executor: Callable[[TaskData], Any]
    ) -> ExecutionResult:  # TODO(TYPE): replace Any with concrete type
        """Route execution through unified gateway."""
        logger.info(
            f"[GATEWAY] Path '{self.path_name}' routing task {task.id} through unified gateway"
        )
        return await self.gateway.execute(task, executor)


class EnhancedBaseAgentAdapter(ExecutionPathAdapter):
    """
    Adapter for EnhancedBaseAgent.process_task() (Path 1).

    Wraps synchronous REST-based agent execution through the unified gateway.
    """

    def __init__(self, gateway: UnifiedAgentGateway):
        super().__init__(gateway, "EnhancedBaseAgent.process_task")


class OrchestratorAdapter(ExecutionPathAdapter):
    """
    Adapter for PerfectOrchestrator + SubagentManager (Path 2).

    Wraps orchestration-based multi-agent execution through the unified gateway.
    """

    def __init__(self, gateway: UnifiedAgentGateway):
        super().__init__(gateway, "PerfectOrchestrator+SubagentManager")


class CVAStateMachineAdapter(ExecutionPathAdapter):
    """
    Adapter for CVA State Machine (Path 3).

    Wraps conversational voice agent state transitions through the unified gateway.
    """

    def __init__(self, gateway: UnifiedAgentGateway):
        super().__init__(gateway, "CVA.StateMachine")


class DramatiqWorkflowAdapter(ExecutionPathAdapter):
    """
    Adapter for Dramatiq Async Workflow (Path 4).

    Wraps background task execution through the unified gateway.
    """

    def __init__(self, gateway: UnifiedAgentGateway):
        super().__init__(gateway, "Dramatiq.AsyncWorkflow")


class SubAgentFactoryAdapter(ExecutionPathAdapter):
    """
    Adapter for SubAgent Factory - M-MDP (Path 5).

    Wraps multi-MDP agent execution through the unified gateway.
    """

    def __init__(self, gateway: UnifiedAgentGateway):
        super().__init__(gateway, "SubAgentFactory.M-MDP")


class WebSocketLangGraphAdapter(ExecutionPathAdapter):
    """
    Adapter for WebSocket LangGraph Stream (Path 6).

    Wraps real-time streaming execution through the unified gateway.
    """

    def __init__(self, gateway: UnifiedAgentGateway):
        super().__init__(gateway, "WebSocket.LangGraph")


class GatewayAdapterRegistry:
    """
    Registry of execution path adapters.

    Central point for managing all 6 execution paths unified through the gateway.
    """

    def __init__(self, gateway: UnifiedAgentGateway):
        self.gateway = gateway
        self.adapters: dict[str, ExecutionPathAdapter] = {}

        # Register all 6 execution path adapters
        self._register_adapters()
        logger.info("[GATEWAY] All 6 execution path adapters registered")

    def _register_adapters(self) -> None:
        """Register all execution path adapters."""
        self.adapters["enhanced_base_agent"] = EnhancedBaseAgentAdapter(self.gateway)
        self.adapters["orchestrator"] = OrchestratorAdapter(self.gateway)
        self.adapters["cva_state_machine"] = CVAStateMachineAdapter(self.gateway)
        self.adapters["dramatiq_workflow"] = DramatiqWorkflowAdapter(self.gateway)
        self.adapters["subagent_factory"] = SubAgentFactoryAdapter(self.gateway)
        self.adapters["websocket_langgraph"] = WebSocketLangGraphAdapter(self.gateway)

    def get_adapter(self, path_key: str) -> ExecutionPathAdapter | None:
        """Get adapter by key."""
        if path_key not in self.adapters:
            logger.warning(f"[GATEWAY] Unknown execution path: {path_key}")
            return None
        return self.adapters[path_key]

    def get_all_adapters(self) -> dict[str, ExecutionPathAdapter]:
        """Get all registered adapters."""
        return self.adapters

    def get_gateway_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get unified gateway status with all adapters."""
        return {
            "gateway": self.gateway.__class__.__name__,
            "adapters_registered": len(self.adapters),
            "adapter_paths": list(self.adapters.keys()),
            "circuit_breakers": self.gateway.get_all_breaker_statuses(),
            "config": {
                "enable_ethics_gate": self.gateway.config.enable_ethics_gate,
                "enable_oversight_gate": self.gateway.config.enable_oversight_gate,
                "enable_authority_check": self.gateway.config.enable_authority_check,
                "enable_circuit_breaker": self.gateway.config.enable_circuit_breaker,
                "default_timeout_seconds": self.gateway.config.default_timeout_seconds,
            },
        }
