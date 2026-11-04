"""
Abstract Interfaces for Workflow Engine Dependencies
Enables dependency injection and testability (C.7 requirement)

Design Pattern: Dependency Inversion Principle
- WorkflowEngine depends on abstractions, not concrete implementations
- Tests can inject fakes/mocks without modifying engine code
- Production injects real LLM/Tool/Agent providers
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Optional

# ============================================================================
# DATA TRANSFER OBJECTS
# ============================================================================


@dataclass
class TaskExecutionRequest:
    """Request to execute a task"""

    task_id: str
    task_type: str
    agent_type: str
    parameters: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    tenant_id: str | None = None
    timeout: int = 300  # seconds


@dataclass
class TaskExecutionResult:
    """Result of task execution"""

    task_id: str
    success: bool
    output: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    error: str | None = None
    execution_time: float = 0.0
    provider_used: str | None = None
    tokens_used: int | None = None
    #: Een mislukte stap die het waard is opnieuw te proberen (netwerk, time-out, te druk); standaard niet.
    tijdelijk: bool = False


# ============================================================================
# PROVIDER INTERFACES
# ============================================================================


class ILLMProvider(ABC):
    """
    Abstract interface for LLM providers (OpenAI, Anthropic, etc.)

    Purpose: Decouple workflow engine from specific LLM implementations
    Testing: Inject FakeLLMProvider that returns deterministic outputs
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Generate text completion

        Returns:
            {
                "content": str,
                "provider": str,
                "model": str,
                "tokens": int,
                "finish_reason": str
            }
        """
        pass

    @abstractmethod
    async def embed(self, text: str, model: str = "text-embedding-ada-002") -> list[float]:
        """Generate text embedding"""
        pass

    @abstractmethod
    async def moderate(self, text: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Content moderation check"""
        pass


class IToolBroker(ABC):
    """
    Abstract interface for tool execution

    Purpose: Decouple from HTTP calls, scripts, external APIs
    Testing: Inject FakeToolBroker with predetermined results
    """

    @abstractmethod
    async def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        timeout: int = 60,
        tenant_id: int | None = None,
        starter: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Execute a tool/action

        `starter` is de mens die de workflow startte (`initiated_by`); een toolstap mag niet meer dan hij.

        Returns:
            {
                "success": bool,
                "result": Any,
                "error": Optional[str],
                "execution_time": float
            }
        """
        pass

    @abstractmethod
    async def list_available_tools(self) -> list[str]:
        """Get list of available tools"""
        pass


class IAgentRuntime(ABC):
    """
    Abstract interface for agent loading and execution

    Purpose: Decouple from SubAgent loader implementation
    Testing: Inject FakeAgentRuntime with mock agents
    """

    @abstractmethod
    async def load_agent(self, agent_type: str) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Load agent by type"""
        pass

    @abstractmethod
    async def execute_agent(
        self, agent: Any, task_request: TaskExecutionRequest  # TODO(TYPE): replace Any with concrete type
    ) -> TaskExecutionResult:
        """Execute agent with task"""
        pass

    @abstractmethod
    async def run_agent(
        self,
        agent_id: str,
        instruction: str,
        context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Run agent with instruction (simplified interface for workflow engine)

        Args:
            agent_id: Agent identifier
            instruction: Instruction text for the agent
            context: Execution context with variables

        Returns: Dict[str, Any] with agent output  # TODO(TYPE): replace Any with concrete type
        """
        pass

    async def run_agentstap(
        self,
        agent_id: str,
        instruction: str,
        context: dict[str, object],
        starter: str | None = None,
    ) -> dict[str, object]:
        """Voer een AGENTSTAP uit: de gekozen agent, met alleen de rechten van de starter.

        Niet abstract: een runtime die dit niet implementeert weigert (fail-closed) in plaats van de stap
        stilletjes door een andere weg te laten lopen. `context["tenant_id"]` komt van de uitvoering.
        """
        reden = "deze agent kan nog niet in een workflow draaien"
        return {"success": False, "agent_id": agent_id, "error": reden, "output": {"error": reden}}

    @abstractmethod
    async def get_available_agents(self) -> list[str]:
        """Get list of available agent types"""
        pass


class IWorkflowEngine(ABC):
    """
    Abstract interface for workflow engine

    Purpose: Enable testing of orchestrator/worker without full engine
    """

    @abstractmethod
    async def register_workflow(
        self,
        workflow_id: str,
        spec_json: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        tenant_id: str | None = None,
    ) -> str:
        """Register new workflow, returns workflow_id"""
        pass

    @abstractmethod
    async def validate_workflow(self, workflow_id: str) -> tuple[bool, str | None]:
        """
        Validate workflow DAG

        Returns: Tuple[Any, ...] of (is_valid, error_message)  # TODO(TYPE): replace Any with concrete type
        """
        pass

    @abstractmethod
    async def execute_workflow(
        self,
        execution_id: str,
        uow: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Execute entire workflow (orchestration logic), returns execution summary
        """
        pass

    @abstractmethod
    async def execute_task(self, execution_id: str, task_ref: str) -> TaskExecutionResult:
        """
        Execute single task (called by worker)

        This is the KEY seam for testing:
        - Production: Calls real LLM/Tool/Agent providers
        - Tests: Uses injected fakes
        """
        pass

    @abstractmethod
    async def get_execution(self, execution_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get execution status"""
        pass

    @abstractmethod
    async def list_executions(
        self,
        workflow_id: str | None = None,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """List executions with filters"""
        pass

    @abstractmethod
    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel running execution"""
        pass


# ============================================================================
# STATE MACHINE INTERFACE
# ============================================================================


class IStateMachine(ABC):
    """
    Abstract interface for state transition validation

    Purpose: Enforce state machine rules for workflow/task status
    """

    @abstractmethod
    def can_transition(
        self,
        from_status: str,
        to_status: str,
        entity_type: str = "workflow",  # "workflow" or "task"
    ) -> bool:
        """Check if state transition is allowed"""
        pass

    @abstractmethod
    def get_allowed_transitions(
        self, current_status: str, entity_type: str = "workflow"
    ) -> list[str]:
        """Get list of allowed next states"""
        pass

    @abstractmethod
    def validate_transition(
        self, from_status: str, to_status: str, entity_type: str = "workflow"
    ) -> None:
        """Validate transition and raise ValueError if invalid"""
        pass


# ============================================================================
# QUEUE INTERFACE (for future Dramatiq/Celery abstraction)
# ============================================================================


class ITaskQueue(ABC):
    """
    Abstract interface for task queue (Dramatiq/Celery/Redis)

    Purpose: Enable swapping queue implementations
    """

    @abstractmethod
    async def enqueue_task(
        self,
        queue_name: str,
        task_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        priority: int = 5,
        delay_seconds: int = 0,
    ) -> str:
        """Enqueue task, returns task_id"""
        pass

    @abstractmethod
    async def get_queue_depth(self, queue_name: str) -> int:
        """Get number of pending tasks in queue"""
        pass


# ============================================================================
# UNIT OF WORK INTERFACE (P5 - Futureproof Transaction Management)
# ============================================================================


class IUnitOfWork(ABC):
    """
    Abstract Unit of Work interface for explicit transaction management

    Design Pattern: Unit of Work (Martin Fowler, PoEAA)

    Purpose:
    - Explicit transaction boundaries (no implicit commits)
    - Clean separation between business logic and persistence
    - Perfect test isolation (auto-rollback in tests)
    - Supports nested transactions via savepoints

    Benefits:
    1. Engine methods don't control commit timing - caller decides
    2. Tests get auto-rollback without special handling
    3. Production gets explicit commit points
    4. Parallel tests can each have isolated transactions
    5. Exception handling is clean (auto-rollback in __aexit__)

    Usage in Production:
        async with ProductionUnitOfWork(session_maker) as uow:
            workflow_id = await engine.create_workflow(uow, spec)
            execution_id = await engine.start_execution(uow, workflow_id)
            await uow.commit()  # Explicit commit

    Usage in Tests:
        async with TestUnitOfWork(test_session) as uow:
            workflow_id = await engine.create_workflow(uow, spec)
            # Auto-rollback at end - clean slate for next test
    """

    @abstractmethod
    async def __aenter__(self) -> "IUnitOfWork":
        """Enter transaction context"""
        pass

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit transaction context (rollback on exception)"""
        pass

    @abstractmethod
    async def commit(self) -> None:
        """
        Explicitly commit all changes in this unit of work

        Note: Only call this when you want changes to persist.
        In tests, typically don't call this to get auto-rollback.
        """
        pass

    @abstractmethod
    async def rollback(self) -> None:
        """Explicitly rollback all changes in this unit of work"""
        pass

    @property
    @abstractmethod
    def session(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """
        Access to underlying database session

        Returns: AsyncSession (or compatible interface)

        Use this to perform queries and add entities:
            uow.session.add(entity)
            result = await uow.session.execute(query)
        """
        pass
