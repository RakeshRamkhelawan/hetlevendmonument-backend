"""
Core interfaces and protocols for the Sanskriti Setu AI Multi-Agent System
Defines the foundational contracts that all components must implement
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel, Field, field_validator

from src.core.shared.agent_context import AgentExecutionContext

# Import types from single source of truth
from src.core.types import (
    AgentType,
    ExecutionStatusContract,
    IsolationLevel,
    TaskPriority,
    TaskStatus,
)

__all__ = [
    "AgentType",
    "ExecutionStatusContract",
    "IsolationLevel",
    "TaskPriority",
    "TaskStatus",
    "TaskData",
    "ExecutionResult",
    "TaskResult",
    "AgentCapability",
    "AgentStatus",
    "SandboxEnvironment",
    "ApprovalRequest",
    "Agent",
    "SandboxManager",
    "EventEmitter",
    "BaseAgent",
    "SystemEvent",
    "TaskRepository",
    "ExecutionRepository",
    "SystemConfig",
    "IAgentRepository",
    "IAgentRegistryRepository",
    "IRedisRepository",
    "AsyncSessionFactory",
]

# NOTE: AsyncSession is imported here (not under TYPE_CHECKING) because
# AsyncSessionFactory is a runtime alias, not just a type annotation.
# SQLAlchemy is a project-wide dependency so this import is safe.
# Agents that need a session factory receive it from outside -- they never
# import src.core.database.database directly (ADR-034).
AsyncSessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


# Core Data Models
class TaskData(BaseModel):
    """Core task data structure"""

    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:8]}")
    title: str
    description: str
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    assigned_to: str | None = None
    estimated_duration: int | None = None  # in minutes
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    code: str | None = None  # Optional code to execute in sandbox
    company_context: AgentExecutionContext | None = Field(
        default=None,
        description="Company execution context for Golden Rule R1 enforcement",
        exclude=True,  # Never serialised to JSON - stays in-process
    )
    # Phase A: Unified Gateway fields
    agent_id: str | None = None
    tenant_id: int | None = None
    execution_deadline: datetime | None = Field(
        default=None,
        description="Deadline for execution completion (Phase A timeout propagation)",
    )
    # GDPR & Privacy (Cluster 5)
    data_category: str = Field(
        default="general",
        description="Data classification category (e.g. general, sensitive, restricted)",
    )
    contains_pii: bool = Field(
        default=False,
        description="Flag indicating if task parameters/metadata contain PII",
    )

    @field_validator("company_context", mode="before")
    @classmethod
    def refuse_anything_but_a_context(cls, v: object) -> AgentExecutionContext | None:
        """Alleen een echt AgentExecutionContext of None; nooit een dict.

        Waarom mode="before" en niet het type alleen (gemeten 2026-09-10). Het veld
        droeg `Any | None` met een isinstance-validator erachter; die weigerde elke
        dict. Met het echte type erop bouwt pydantic van een complete dict zelf een
        AgentExecutionContext, en een validator in de standaard modus ("after") ziet
        dan al het gebouwde object en laat hem door. Gemeten: `Field(strict=True)`
        houdt dat NIET tegen op dit veld -- `ctx.model_dump()` werd gewoon aangenomen.
        Alleen mode="before" ziet de ruwe invoer en kan hem weigeren.

        Dat het strikt blijft is geen smaak: `exclude=True` zegt dat dit veld het
        proces nooit verlaat, en Golden Rule R1 leunt erop dat hier een echt,
        in-process opgebouwd context-object staat en niet iets dat uit JSON is
        nagemaakt. Het parametertype is `object` en niet `Any`: de invoer is hier
        werkelijk onbekend, en `object` dwingt af dat we hem eerst controleren.

        Beide richtingen staan vast in tests/core/company/test_task_data_context.py:
        een instantie komt er ongewijzigd door (identiteit), elke dict faalt.
        """
        if v is None or isinstance(v, AgentExecutionContext):
            return v
        raise ValueError(
            f"company_context must be AgentExecutionContext or None, got {type(v).__name__}"
        )

    @property
    def parameters(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Alias for metadata - used by generated agents for task parameters."""
        return self.metadata

    @property
    def task_id(self) -> str:
        """Alias for id - used by consumers expecting task_id field."""
        return self.id

    @property
    def context(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Alias for metadata - used by agents expecting context field."""
        return self.metadata

    @property
    def payload(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Alias for metadata - used by agents expecting payload field."""
        return self.metadata

    @property
    def type(self) -> str:
        """Alias for title - used by ALS for task type routing."""
        return self.title


class ExecutionResult(BaseModel):
    """Result of a task execution"""

    task_id: str
    success: bool
    result_data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    error_message: str | None = None
    execution_time: float = 0.0  # in seconds
    confidence_score: float = 1.0  # 0.0 to 1.0 (Fix: arbitration)
    reasoning_path: list[str] = Field(
        default_factory=list
    )  # Step-by-step logic (Fix: transparency)
    resource_usage: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # Metrics like API calls, token usage
    data_category: str = Field(
        default="general",
        description="Data classification category for result data",
    )
    contains_pii: bool = Field(
        default=False,
        description="Flag indicating if result data contains PII",
    )
    logs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tenant_id: int | None = None  # Ensure tenant context is preserved
    agent_id: str | None = None
    output: str | None = None
    status: ExecutionStatusContract | None = None
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    @property
    def data(self) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Alias for result_data."""
        return self.result_data

    @property
    def error(self) -> str | None:
        """Alias for error_message."""
        return self.error_message


class TaskResult(BaseModel):
    """Result of agent task processing - specialized for agent workflows"""

    task_id: str
    agent_id: str
    result: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    success: bool = True
    execution_time: float = 0.0  # in seconds
    metadata: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    error_message: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentCapability(BaseModel):
    """Describes what an agent can do"""

    name: str
    description: str
    input_types: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    resource_requirements: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    estimated_duration: int | None = None


class AgentStatus(BaseModel):
    """Current status of an agent"""

    agent_id: str
    agent_type: AgentType
    is_active: bool = True
    current_load: float = 0.0  # 0.0 to 1.0
    capabilities: list[AgentCapability] = Field(default_factory=list)
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


class SandboxEnvironment(BaseModel):
    """Sandbox environment configuration"""

    id: str = Field(default_factory=lambda: f"sandbox_{uuid.uuid4().hex[:8]}")
    isolation_level: IsolationLevel
    resource_limits: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    allowed_capabilities: list[str] = Field(default_factory=list)
    network_access: bool = False
    filesystem_access: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    runtime_requirements: dict[str, Any] = Field(
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApprovalRequest(BaseModel):
    """Request for human approval"""

    id: str = Field(default_factory=lambda: f"approval_{uuid.uuid4().hex[:8]}")
    task_id: str
    requesting_agent: str
    approval_type: str
    description: str
    risk_level: int = Field(ge=1, le=10)  # 1=low, 10=critical
    context: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    approved: bool | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None


# Protocol Interfaces
@runtime_checkable
class Agent(Protocol):
    """Core agent protocol - all agents must implement this"""

    @property
    def agent_id(self) -> str:
        """Unique identifier for this agent"""
        ...

    @property
    def agent_type(self) -> AgentType:
        """Type of this agent"""
        ...

    @property
    def address(self) -> str:
        """Address/location of this agent for communication"""
        ...

    async def process_task(self, task: TaskData) -> ExecutionResult:
        """Process a task and return result"""
        ...

    async def get_capabilities(self) -> list[AgentCapability]:
        """Get list of capabilities this agent supports"""
        ...

    async def get_status(self) -> AgentStatus:
        """Get current status of this agent"""
        ...


@runtime_checkable
class SandboxManager(Protocol):
    """Sandbox management protocol"""

    async def create_sandbox(self, config: SandboxEnvironment) -> str:
        """Create a new sandbox environment"""
        ...

    async def execute_in_sandbox(self, sandbox_id: str, task: TaskData) -> ExecutionResult:
        """Execute task in specified sandbox"""
        ...

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        """Destroy sandbox and cleanup resources"""
        ...

    async def get_sandbox_status(
        self, sandbox_id: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current status of sandbox"""
        ...


@runtime_checkable
class EventEmitter(Protocol):
    """Event emission protocol for system-wide communication"""

    async def emit_event(
        self, event_type: str, data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Emit an event to the system"""
        ...


# Abstract Base Classes
class BaseAgent(ABC):
    """Abstract base class for all agents"""

    def __init__(self, agent_id: str, agent_type: AgentType, **kwargs: Any) -> None:
        self._agent_id = agent_id
        self._agent_type = agent_type
        self._is_active = True
        self._current_load = 0.0
        self._capabilities: list[AgentCapability] = []

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def agent_type(self) -> AgentType:
        return self._agent_type

    @property
    def address(self) -> str:
        """Default runtime address used by protocol-based callers."""
        return getattr(self, "_address", self._agent_id)

    @address.setter
    def address(self, value: str) -> None:
        self._address = value

    @abstractmethod
    async def process_task(self, task: TaskData) -> ExecutionResult:
        """Process a task - must be implemented by subclasses"""

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the agent - must be implemented by subclasses"""

    async def get_capabilities(self) -> list[AgentCapability]:
        """Get agent capabilities - can be overridden"""
        return self._capabilities

    async def get_status(self) -> AgentStatus:
        """Get current agent status"""
        return AgentStatus(
            agent_id=self._agent_id,
            agent_type=self._agent_type,
            is_active=self._is_active,
            current_load=self._current_load,
            capabilities=self._capabilities,
            last_heartbeat=datetime.now(timezone.utc),
        )

    async def validate_task(self, task: TaskData) -> bool:
        """Validate if this agent can handle the task"""
        return True  # Default implementation

    async def emit_event(
        self, event_type: str, data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Emit an event - default no-op implementation"""


# System Events
class SystemEvent(BaseModel):
    """System event data structure"""

    id: str = Field(default_factory=lambda: f"event_{uuid.uuid4().hex[:8]}")
    event_type: str
    source: str
    data: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    severity: str = "info"  # debug, info, warning, error, critical


# Database Repository Protocols
@runtime_checkable
class TaskRepository(Protocol):
    """Task data repository protocol"""

    async def create_task(self, task: TaskData) -> str:
        """Create a new task"""
        ...

    async def get_task(self, task_id: str) -> TaskData | None:
        """Get task by ID"""
        ...

    async def update_task(self, task: TaskData) -> bool:
        """Update existing task"""
        ...

    async def list_tasks(self, status: TaskStatus | None = None) -> list[TaskData]:
        """List tasks, optionally filtered by status"""
        ...


@runtime_checkable
class ExecutionRepository(Protocol):
    """Execution result repository protocol"""

    async def store_result(self, result: ExecutionResult) -> str:
        """Store execution result"""
        ...

    async def get_results(self, task_id: str) -> list[ExecutionResult]:
        """Get all results for a task"""
        ...


# Configuration
class SystemConfig(BaseModel):
    """System-wide configuration"""

    environment: str = "development"
    debug: bool = True

    # Database
    database_url: str = "sqlite:///./sanskriti_setu.db"
    database_pool_size: int = 5

    # API
    api_host: str = "0.0.0.0"  # nosec B104: Docker networking (Traefik secures)
    api_port: int = 8000

    # Security
    secret_key: str = "dev-secret-key-change-in-production"
    access_token_expire_minutes: int = 30

    # Feature Flags (Week-based rollout)
    feature_flags: dict[str, bool] = Field(
        default_factory=lambda: {
            "real_docker_sandbox": True,  # Week 2 - Production enabled
            "multi_agent_orchestration": False,  # Week 2
            "ml_ethics_engine": False,  # Week 3
            "knowledge_evolution": False,  # Week 3
            "advanced_ui": False,  # Week 3
        }
    )

    # Sandbox
    default_isolation_level: IsolationLevel = IsolationLevel.MOCK
    sandbox_timeout: int = 300  # 5 minutes

    # Agent Configuration
    max_concurrent_tasks: int = 10
    agent_heartbeat_interval: int = 30  # seconds

    # External Services
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None


# Agent Repository Protocols (ADR-034 ss2.1: protocol interfaces live in shared/)
@runtime_checkable
class IAgentRepository(Protocol):
    """Repository protocol for Agent ORM model access.

    NOTE: runtime_checkable only verifies that required method *names* exist at
    runtime -- it does not check signatures or async-ness. Full structural
    conformance is enforced by pyright at type-check time.

    NOTE: Return types use Any intentionally, en de reden hieronder is op
    2026-09-10 nagemeten omdat de eerdere formulering ("would create a circular
    dependency") niet klopte voor de enige import die hier nodig is. Een import
    onder `if TYPE_CHECKING:` bestaat op runtime niet en kan dus geen cyclus maken,
    en geen enkel import-linter-contract in `.importlinter` verbiedt de richting
    src.core.shared -> src.core.agents (Contract 7 verbiedt agents -> database, niet
    dit). Wat er WEL in de weg staat, gemeten en niet aangenomen:

      1. Naamconflict in precies dit bestand. `Agent` is hier al een Protocol
         (regel 285 op het moment van schrijven) en `src.core.agents.models.Agent`
         is de ORM-rij. De ORM-klasse zou dus onder een alias moeten binnenkomen in
         het meest geimporteerde bestand van de codebase: `git grep -l shared.interfaces`
         geeft 273 bestanden onder src/ en 115 onder tests/ (gemeten 2026-09-10; hier
         stond eerst 111 voor tests/, en dat getal kwam met geen enkele query terug --
         betrapt door de tweede Gate-2-reviewer). Twee dingen die `Agent` heten in een
         bestand dat iedereen importeert is een grotere fout dan negen `Any`.
      2. De winst is klein: er zijn twee concrete implementaties
         (`agents/repositories/agent_repository.py`,
         `agents/repositories/agent_registry_repository.py`) en hun conformiteit
         staat al vast in tests/unit/agents/test_agent_repository_protocol.py en
         test_agent_registry_repository.py met een runtime-isinstance op het
         Protocol.

    Deze negen `Any` blijven dus bewust staan. De volledige meting staat in ADR-036
    rij OP-232 (die rij gaat over de stand van de Any-schuld als geheel; een eigen rij
    voor deze negen bestond niet, en die verwijzing stond hier eerst wel -- betrapt door
    de tweede Gate-2-reviewer op 2026-09-10).
    """

    async def get_agent_by_id(self, agent_id: int, tenant_id: int) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Return Agent by surrogate PK, filtered by tenant_id. Returns None if not found or wrong tenant."""
        ...

    async def get_agents_by_tenant(
        self, tenant_id: int, limit: int = 50, offset: int = 0
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Return paginated list of Agents for a tenant."""
        ...

    async def save_agent(self, agent: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Persist (add + flush) an Agent. Caller owns the transaction."""
        ...


@runtime_checkable
class IAgentRegistryRepository(Protocol):
    """Repository protocol for RegisteredAgent ORM model access.

    NOTE: runtime_checkable only verifies method names at runtime.
    NOTE: Any return types are intentional -- see IAgentRepository docstring.
    """

    async def get_registered_agent_by_agent_id(self, agent_id: str, tenant_id: int) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Return RegisteredAgent by business-key agent_id and tenant_id."""
        ...

    async def get_registered_agents(
        self, tenant_id: int, limit: int = 50, offset: int = 0
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Return paginated list of all RegisteredAgents for a tenant."""
        ...

    async def get_active_agents(
        self, tenant_id: int, limit: int = 50, offset: int = 0
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Return paginated list of active (recently heartbeated) agents for a tenant."""
        ...

    async def register_agent(self, registration: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Persist a RegisteredAgent. Caller owns the transaction."""
        ...

    async def update_agent(self, agent_id: str, tenant_id: int, values: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Update fields on an existing RegisteredAgent. Caller owns the transaction."""
        ...

    async def delete_agent(self, agent_id: str, tenant_id: int) -> None:
        """Delete a RegisteredAgent. Caller owns the transaction."""
        ...


@runtime_checkable
class IRedisRepository(Protocol):
    """Repository protocol for Redis key-value access.

    NOTE: runtime_checkable only verifies method names at runtime.
    Redis GET returns bytes; callers must decode as needed.
    """

    async def get(self, key: str) -> bytes | None:
        """Retrieve a value by key. Returns None if key does not exist."""
        ...

    async def set(self, key: str, value: str | bytes, ttl: int | None = None) -> None:
        """Store a value. ttl is seconds-to-live; None means no expiry."""
        ...

    async def delete(self, key: str) -> None:
        """Delete a key. No-op if key does not exist."""
        ...
