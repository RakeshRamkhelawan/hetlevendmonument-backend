"""
ACP Protocol: Swarm Stream Service

Multi-agent swarm orchestration with real-time streaming.
Agent roles: Orchestrator, Researcher, Executor
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, cast
from collections.abc import AsyncGenerator, Callable

logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Types
# ============================================================================


class AgentRole(str, Enum):
    """Agent roles in the swarm."""

    ORCHESTRATOR = "orchestrator"
    RESEARCHER = "researcher"
    EXECUTOR = "executor"


class AgentStatus(str, Enum):
    """Agent execution status."""

    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    COMPLETE = "complete"
    ERROR = "error"


class EventType(str, Enum):
    """Swarm event types."""

    SWARM_STARTED = "swarm_started"
    AGENT_SPAWNED = "agent_spawned"
    AGENT_STATUS_CHANGED = "agent_status_changed"
    AGENT_MESSAGE = "agent_message"
    FEEDBACK_REQUESTED = "feedback_requested"
    FEEDBACK_RECEIVED = "feedback_received"
    TASK_DELEGATED = "task_delegated"
    TASK_COMPLETED = "task_completed"
    SWARM_COMPLETE = "swarm_complete"
    SWARM_ERROR = "swarm_error"


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class SwarmAgent:
    """Represents an agent in the swarm."""

    id: str
    role: AgentRole
    name: str
    status: AgentStatus = AgentStatus.IDLE
    current_task: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "id": self.id,
            "role": self.role.value,
            "name": self.name,
            "status": self.status.value,
            "current_task": self.current_task,
            "message_count": len(self.messages),
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class SwarmEvent:
    """Event emitted by the swarm for real-time streaming."""

    id: str
    type: EventType
    timestamp: datetime
    agent_id: str | None
    agent_role: AgentRole | None
    message: str
    data: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "agent_role": self.agent_role.value if self.agent_role else None,
            "message": self.message,
            "data": self.data,
        }


@dataclass
class SwarmSession:
    """Active swarm session."""

    id: str
    tenant_id: int
    objective: str
    agents: dict[str, SwarmAgent] = field(default_factory=dict)
    events: list[SwarmEvent] = field(default_factory=list)
    status: str = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "objective": self.objective,
            "agents": {k: v.to_dict() for k, v in self.agents.items()},
            "event_count": len(self.events),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


# ============================================================================
# Swarm Stream Service
# ============================================================================


class SwarmStreamService:
    """
    Multi-agent swarm orchestration service with real-time streaming.

    Features:
    - Agent role management (Orchestrator, Researcher, Executor)
    - Real-time event streaming via callbacks
    - Dynamic feedback loops
    - Multi-tenant isolation
    """

    def __init__(self, tenant_id: int = 1) -> None:
        self.tenant_id = tenant_id
        self._sessions: dict[str, SwarmSession] = {}
        self._event_callbacks: list[Callable[..., Any]] = []  # TODO(TYPE): replace Any with concrete type
        self._feedback_handlers: dict[str, asyncio.Future[Any]] = {}  # TODO(TYPE): replace Any with concrete type

    # ========================================================================
    # Event Management
    # ========================================================================

    def add_event_callback(self, callback: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Add a callback for real-time event streaming."""
        self._event_callbacks.append(callback)

    def remove_event_callback(self, callback: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Remove an event callback."""
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)

    async def _emit_event(self, event: SwarmEvent) -> None:
        """Emit event to all registered callbacks."""
        for callback in self._event_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")

    def _create_event(
        self,
        session: SwarmSession,
        event_type: EventType,
        message: str,
        agent: SwarmAgent | None = None,
        data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> SwarmEvent:
        """Create and record a swarm event."""
        event = SwarmEvent(
            id=str(uuid.uuid4()),
            type=event_type,
            timestamp=datetime.now(timezone.utc),
            agent_id=agent.id if agent else None,
            agent_role=agent.role if agent else None,
            message=message,
            data=data or {},
        )
        session.events.append(event)
        return event

    # ========================================================================
    # Agent Management
    # ========================================================================

    def _spawn_agent(
        self, session: SwarmSession, role: AgentRole, name: str | None = None
    ) -> SwarmAgent:
        """Spawn a new agent in the swarm."""
        agent_id = str(uuid.uuid4())[:8]

        default_names = {
            AgentRole.ORCHESTRATOR: "Coordinator Alpha",
            AgentRole.RESEARCHER: "Analyst Beta",
            AgentRole.EXECUTOR: "Worker Gamma",
        }

        agent = SwarmAgent(
            id=agent_id,
            role=role,
            name=name or default_names.get(role, f"{role.value.title()}-{agent_id[:4]}"),
        )

        session.agents[agent_id] = agent
        return agent

    async def _update_agent_status(
        self,
        session: SwarmSession,
        agent: SwarmAgent,
        status: AgentStatus,
        task: str | None = None,
    ) -> None:
        """Update agent status and emit event."""
        agent.status = status
        if task:
            agent.current_task = task

        event = self._create_event(
            session,
            EventType.AGENT_STATUS_CHANGED,
            f"{agent.name} is now {status.value}",
            agent,
            {"new_status": status.value, "task": task},
        )
        await self._emit_event(event)

    async def _agent_message(
        self,
        session: SwarmSession,
        agent: SwarmAgent,
        message: str,
        data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Agent sends a message to the stream."""
        agent.messages.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": message,
                "data": data,
            }
        )

        event = self._create_event(session, EventType.AGENT_MESSAGE, message, agent, data)
        await self._emit_event(event)

    # ========================================================================
    # Feedback Loops
    # ========================================================================

    async def request_feedback(
        self,
        session: SwarmSession,
        agent: SwarmAgent,
        question: str,
        options: list[str],
        timeout: float = 60.0,
    ) -> str | None:
        """
        Request feedback from user during swarm execution.
        Returns the selected option or None if timeout.
        """
        feedback_id = str(uuid.uuid4())[:8]

        event = self._create_event(
            session,
            EventType.FEEDBACK_REQUESTED,
            question,
            agent,
            {"feedback_id": feedback_id, "options": options},
        )
        await self._emit_event(event)

        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self._feedback_handlers[feedback_id] = future

        try:
            result = await asyncio.wait_for(future, timeout=timeout)

            # Emit feedback received event
            received_event = self._create_event(
                session,
                EventType.FEEDBACK_RECEIVED,
                f"User selected: {result}",
                agent,
                {"feedback_id": feedback_id, "response": result},
            )
            await self._emit_event(received_event)

            return cast(Optional[str], result)
        except TimeoutError:
            logger.warning(f"Feedback timeout for {feedback_id}")
            return None
        finally:
            self._feedback_handlers.pop(feedback_id, None)

    def submit_feedback(self, feedback_id: str, response: str) -> None:
        """Submit feedback response from user."""
        if feedback_id in self._feedback_handlers:
            self._feedback_handlers[feedback_id].set_result(response)

    # ========================================================================
    # Swarm Execution
    # ========================================================================

    async def start_swarm(self, objective: str, auto_spawn: bool = True) -> SwarmSession:
        """
        Start a new swarm session for the given objective.

        Args:
            objective: The goal for the swarm to achieve
            auto_spawn: Whether to automatically spawn default agents

        Returns:
            The created SwarmSession
        """
        session_id = str(uuid.uuid4())

        session = SwarmSession(id=session_id, tenant_id=self.tenant_id, objective=objective)
        self._sessions[session_id] = session

        # Emit swarm started event
        event = self._create_event(
            session,
            EventType.SWARM_STARTED,
            f"Swarm initialized for: {objective}",
            data={"objective": objective},
        )
        await self._emit_event(event)

        # Auto-spawn agents if requested
        if auto_spawn:
            orchestrator = self._spawn_agent(session, AgentRole.ORCHESTRATOR)
            researcher = self._spawn_agent(session, AgentRole.RESEARCHER)
            executor = self._spawn_agent(session, AgentRole.EXECUTOR)

            for agent in [orchestrator, researcher, executor]:
                spawn_event = self._create_event(
                    session,
                    EventType.AGENT_SPAWNED,
                    f"{agent.name} joined the swarm",
                    agent,
                )
                await self._emit_event(spawn_event)

        return session

    async def execute_swarm(self, session: SwarmSession, simulate: bool = True) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Execute the swarm to achieve the objective.

        Args:
            session: The swarm session to execute
            simulate: Whether to simulate execution (for demo)

        Returns:
            Execution result
        """
        try:
            agents = list(session.agents.values())
            orchestrator = next((a for a in agents if a.role == AgentRole.ORCHESTRATOR), None)
            researcher = next((a for a in agents if a.role == AgentRole.RESEARCHER), None)
            executor = next((a for a in agents if a.role == AgentRole.EXECUTOR), None)

            if simulate:
                # Simulated execution flow

                # 1. Orchestrator analyzes objective
                if orchestrator:
                    await self._update_agent_status(
                        session,
                        orchestrator,
                        AgentStatus.THINKING,
                        "Analyzing objective",
                    )
                    await asyncio.sleep(0.5)
                    await self._agent_message(
                        session, orchestrator, f"Breaking down: {session.objective}"
                    )
                    await asyncio.sleep(0.3)
                    await self._agent_message(session, orchestrator, "Delegating research task")

                    # Delegate to researcher
                    delegate_event = self._create_event(
                        session,
                        EventType.TASK_DELEGATED,
                        "Research task assigned",
                        orchestrator,
                        {
                            "to_agent": researcher.id if researcher else None,
                            "task": "Gather requirements",
                        },
                    )
                    await self._emit_event(delegate_event)

                # 2. Researcher gathers info
                if researcher:
                    await self._update_agent_status(
                        session,
                        researcher,
                        AgentStatus.THINKING,
                        "Gathering information",
                    )
                    await asyncio.sleep(0.8)
                    await self._agent_message(
                        session, researcher, "Analyzing relevant data sources..."
                    )
                    await asyncio.sleep(0.5)
                    await self._agent_message(session, researcher, "Found 3 relevant patterns")
                    await self._update_agent_status(session, researcher, AgentStatus.COMPLETE)

                # 3. Executor performs action
                if executor:
                    await self._update_agent_status(
                        session,
                        executor,
                        AgentStatus.EXECUTING,
                        "Implementing solution",
                    )
                    await asyncio.sleep(1.0)
                    await self._agent_message(session, executor, "Applying changes...")
                    await asyncio.sleep(0.5)
                    await self._agent_message(session, executor, "Changes applied successfully")

                    complete_event = self._create_event(
                        session,
                        EventType.TASK_COMPLETED,
                        "Execution completed",
                        executor,
                        {"success": True},
                    )
                    await self._emit_event(complete_event)
                    await self._update_agent_status(session, executor, AgentStatus.COMPLETE)

                # 4. Orchestrator finalizes
                if orchestrator:
                    await self._update_agent_status(session, orchestrator, AgentStatus.COMPLETE)

            # Mark session complete
            session.status = "complete"

            final_event = self._create_event(
                session,
                EventType.SWARM_COMPLETE,
                "Swarm objective achieved",
                data={"objective": session.objective, "result": "success"},
            )
            await self._emit_event(final_event)

            return {
                "success": True,
                "session_id": session.id,
                "events_count": len(session.events),
                "agents": [a.to_dict() for a in session.agents.values()],
            }

        except Exception as e:
            session.status = "error"

            logger.error("Swarm failed: %s: %s", type(e).__name__, e, exc_info=True)
            error_event = self._create_event(
                session,
                EventType.SWARM_ERROR,
                "Swarm failed",
                data={"error": "Swarm failed"},
            )
            await self._emit_event(error_event)

            return {"success": False, "error": "Swarm failed"}

    def get_session(self, session_id: str) -> SwarmSession | None:
        """Get a swarm session by ID."""
        return self._sessions.get(session_id)

    def get_active_sessions(self) -> list[SwarmSession]:
        """Get all active sessions for this tenant."""
        return [s for s in self._sessions.values() if s.status == "active"]


# ============================================================================
# Factory Function
# ============================================================================


def create_swarm_service(tenant_id: int = 1) -> SwarmStreamService:
    """Create a new SwarmStreamService instance."""
    return SwarmStreamService(tenant_id=tenant_id)
