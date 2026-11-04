"""
Chief Visionary Architect (CVA) Agent Implementation
(Refactored: Delegates to modules in src/core/agents/cva/)
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.cva_prompts import get_cva_prompts
from src.core.agents.ethics_gate import get_ethics_gate
from src.core.agents.task_templates import get_task_generator
from src.core.communication.message_protocol import MessagePriority
from src.core.shared.interfaces import AgentCapability, AgentType, ExecutionResult, TaskData

if TYPE_CHECKING:
    from src.core.agents.cva_state_machine import CVAStateMachine
    from src.core.shared.llm_client import LLMClient

from src.core.shared.response_cache import get_response_cache

from .communication_handler import CommunicationHandler
from .llm_handler import LLMHandler
from .memory_handler import MemoryHandler

# Modular handlers
from .models import CVAMode, CVAState
from .state_manager import StateManager

logger = logging.getLogger(__name__)


class CVAAgent(EnhancedBaseAgent):
    """Chief Visionary Architect Agent - The strategic brain of the system (Modular)"""

    def __init__(
        self,
        agent_id: str = "cva_main",
        agent_type: AgentType = AgentType.CVA,
        **kwargs: Any,
    ) -> None:
        super().__init__(agent_id=agent_id, agent_type=agent_type, **kwargs)

        # Initialize modular handlers
        self.state_manager = StateManager(initial_mode=CVAMode.CEO_MODE)
        self.memory_handler = MemoryHandler(agent_id)
        self.communication_handler = CommunicationHandler(agent_id)
        self.llm_handler = LLMHandler(agent_id)

        # Backward compatibility properties
        self.state_machine: "CVAStateMachine" = self.state_manager.state_machine
        # self.cva_state is accessed via property below to ensure sync

        # BaseAgent expects llm_client
        self.llm_client: "LLMClient | None" = self.llm_handler.llm_client

        # CVA-specific configuration
        self.vision_context: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.strategic_objectives: list[str] = []
        self.current_strategy: dict[str, Any] | None = (
            None  # TODO(TYPE): replace Any with concrete type
        )
        self._agent_id_for_communication = agent_id

        # Supporting systems
        self.cva_prompts = get_cva_prompts()
        self.ethics_gate = get_ethics_gate()
        self.response_cache = get_response_cache()
        self.task_generator = get_task_generator()

    async def _initialize_capabilities(self) -> None:
        """Initialize agent capabilities based on role"""
        # CVA has strategic capabilities
        self._capabilities: list[AgentCapability] = []

        # Register strategic capabilities
        await self.register_capability(
            "strategic_planning",
            "Long-term strategic planning and vision setting",
            ["objectives", "constraints", "context"],
            ["strategy", "roadmap", "milestones"],
        )
        await self.register_capability(
            "task_decomposition",
            "Break down complex tasks into manageable subtasks",
            ["complex_task", "project"],
            ["subtasks", "dependencies", "schedule"],
        )
        await self.register_capability(
            "knowledge_synthesis",
            "Synthesize information from multiple sources",
            ["documents", "data", "insights"],
            ["synthesis", "summary", "recommendations"],
        )

    async def register_capability(
        self,
        name: str,
        description: str,
        input_types: list[str],
        output_types: list[str],
    ) -> None:
        """Register a capability with the agent."""
        capability = AgentCapability(
            name=name,
            description=description,
            input_types=input_types,
            output_types=output_types,
            resource_requirements={"memory": "256MB", "cpu": "0.3"},
        )
        self._capabilities.append(capability)

    @property
    def cva_state(self) -> "CVAState":
        return self.state_manager.cva_state

    # --- Delegated Methods ---

    async def initialize_memory_system(self) -> None:
        return await self.memory_handler.initialize()

    async def initialize_communication_system(self) -> None:
        return await self.communication_handler.initialize()

    async def send_strategic_command(
        self,
        command_type: str,
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        recipient_id: str = "ultimate_orchestrator",
        masterprompt: str | None = None,
        priority: MessagePriority = MessagePriority.HIGH,
    ) -> bool:
        return await self.communication_handler.send_strategic_command(
            command_type, parameters, recipient_id, masterprompt, priority
        )

    async def store_strategic_memory(
        self,
        strategy_type: str,
        content: str,
        success_rate: float,
        orchestration_pattern: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        return await self.memory_handler.store_strategic_memory(
            strategy_type, content, success_rate, orchestration_pattern
        )

    async def retrieve_strategic_memories(
        self, query: str, limit: int = 5
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        return await self.memory_handler.retrieve_strategic_memories(query, limit)

    async def transition_to_mode(
        self,
        target_mode: CVAMode,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        return await self.state_manager.transition_to_mode(target_mode, context)

    # --- Core Agent Methods ---

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Process task (required by BaseAgent)"""
        # In a real implementation, this would route to handlers based on task type
        # For refactoring, we provide a basic implementation
        return ExecutionResult(
            task_id=task.id,
            success=True,
            result_data={
                "message": "Task processed via modular CVAAgent",
                "agent_id": self.agent_id,
            },
            logs=["Task processed"],
        )
