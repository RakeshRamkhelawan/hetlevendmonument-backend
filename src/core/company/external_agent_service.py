"""External Agent Service - Heartbeat protocol and task management.

This module implements the ExternalAgentService which manages:
- Agent registration with API key generation
- Heartbeat protocol for health monitoring
- Task assignment and completion
- Stale agent detection
- Tenant isolation

Architecture:
- Uses DatabaseManager for session management
- Uses Redis for heartbeat status caching
- Uses bcrypt for API key hashing
- Integrates with PolicyEngine for output validation
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast

logger = logging.getLogger(__name__)

import bcrypt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.company.models import ExternalAgent
from src.core.company.schemas import (
    ExternalAgentRegister,
    ExternalAgentResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    TaskCompleteRequest,
    TaskNextResponse,
)
from src.core.database.database import DatabaseManager
from src.core.exceptions.exceptions import AuthError, NotFoundError, ValidationError


class ExternalAgentService:
    """Service for managing external agents via heartbeat protocol.

    External agents are AI agents running outside the SanskritiSetu platform
    that can register, send heartbeats, and receive tasks via the API.

    Lifecycle:
    registered -> active -> busy -> stale -> dead

    Security:
    - API keys are shown only once at registration
    - Keys are hashed with bcrypt before storage
    - Tenant isolation on all operations
    """

    # Thresholds
    STALE_MULTIPLIER = 2  # Mark stale after 2x heartbeat_interval
    DEAD_MISSES = 3  # Mark dead after 3 missed heartbeats
    MAX_OUTPUT_SIZE = 10 * 1024 * 1024  # 10MB max output

    def __init__(
        self,
        db_manager: DatabaseManager,
        tenant_context: Any | None,  # TODO(TYPE): replace Any with concrete type
        policy_engine: Any | None,  # TODO(TYPE): replace Any with concrete type
        budget_manager: Any | None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Initialize ExternalAgentService.

        Args:
            db_manager: Database manager for session management
            tenant_context: Tenant context for isolation
            policy_engine: Policy engine for output validation
            budget_manager: Budget manager for token tracking
        """
        self.db_manager = db_manager
        self.tenant_context = tenant_context
        self.policy_engine = policy_engine
        self.budget_manager = budget_manager

    async def register(
        self, data: ExternalAgentRegister
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Register a new external agent.

        Args:
            data: Registration data including name, runtime, capabilities

        Returns:
            dict with agent_id, api_key (plaintext, shown once), heartbeat_endpoint

        Raises:
            ValidationError: If data is invalid
        """
        if self.tenant_context is None:
            raise ValueError("Tenant context required")
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant ID is required")

        async with self.db_manager.get_session() as session:
            # Generate API key (shown only once)
            api_key = self._generate_api_key()
            api_key_hash = bcrypt.hashpw(api_key.encode(), bcrypt.gensalt(rounds=12)).decode()

            # Create agent
            agent = ExternalAgent(
                tenant_id=tenant_id,
                company_id=data.department_id,  # Optional company assignment
                department_id=data.department_id,
                name=data.name,
                runtime=data.runtime,
                capabilities=data.capabilities,
                webhook_url=data.webhook_url,
                api_key_hash=api_key_hash,
                heartbeat_interval_seconds=data.heartbeat_interval_seconds or 30,
                status="registered",
                metrics={"tasks_completed": 0, "tasks_failed": 0},
                config={},
            )

            session.add(agent)
            await session.commit()
            await session.refresh(agent)

            return {
                "agent_id": str(agent.id),
                "api_key": api_key,  # PLAINTEXT - shown only once!
                "heartbeat_endpoint": f"/api/v1/agents/{agent.id}/heartbeat",
                "message": "Store this API key securely - it will not be shown again",
            }

    async def heartbeat(
        self,
        agent_id: uuid.UUID,
        api_key: str,
        data: HeartbeatRequest,
    ) -> HeartbeatResponse:
        """Process heartbeat from external agent.

        Args:
            agent_id: Agent UUID
            api_key: API key for authentication
            data: Heartbeat data including status and metrics

        Returns:
            HeartbeatResponse with ack and pending tasks

        Raises:
            AuthError: If API key is invalid
            NotFoundError: If agent not found
        """
        if self.tenant_context is None:
            raise ValueError("Tenant context required")
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant ID is required")

        async with self.db_manager.get_session() as session:
            # Get agent with tenant check
            agent = await self._get_agent(session, agent_id, tenant_id)
            if agent is None:
                raise NotFoundError(f"Agent {agent_id} not found")

            # Validate API key -- empty string must fail closed, not skip verification
            if not api_key or not bcrypt.checkpw(api_key.encode(), agent.api_key_hash.encode()):
                raise AuthError("Invalid API key")

            # Update heartbeat status
            agent.last_heartbeat_at = datetime.now(timezone.utc)
            agent.status = data.status

            # Update metrics if provided
            if data.metrics:
                agent.metrics.update(data.metrics)

            # Reset missed heartbeat count on successful heartbeat
            if hasattr(agent, "missed_heartbeat_count"):
                agent.missed_heartbeat_count = 0

            await session.commit()

            # Get pending tasks for idle agents
            pending_task_ids: list[str] = []
            if data.status == "idle":
                pending_tasks = await self._get_pending_tasks(session, agent_id, tenant_id)
                # Convert task dicts to task ID strings
                pending_task_ids = [
                    str(t.get("task_id", "")) for t in pending_tasks if t.get("task_id")
                ]

            return HeartbeatResponse(
                ack=True,
                pending_tasks=pending_task_ids,
            )

    async def get_next_task(
        self, agent_id: uuid.UUID, api_key: str | None = None
    ) -> TaskNextResponse | None:
        """Get next pending task for agent.

        Args:
            agent_id: Agent UUID

        Returns:
            TaskNextResponse with task details or None if no tasks
        """
        if self.tenant_context is None:
            raise ValueError("Tenant context required")
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant ID is required")

        async with self.db_manager.get_session() as session:
            agent = await self._get_agent(session, agent_id, tenant_id)
            if agent is None:
                raise NotFoundError(f"Agent {agent_id} not found")

            # api_key=None means caller is internal/trusted (no API-key auth layer involved).
            # Any explicitly-provided value (including empty string) MUST verify -- fail closed.
            if api_key is not None and (
                not api_key or not bcrypt.checkpw(api_key.encode(), agent.api_key_hash.encode())
            ):
                raise AuthError("Invalid API key")

            # Budget check -- LLM-C7-005 (SP-SEC-002)
            # NOTE: When wiring the real BudgetManager, use a factory (not singleton)
            # so each request gets a fresh session. -- SP-SEC-002
            if self.budget_manager is not None:
                budget_result = await self.budget_manager.check_budget(
                    tenant_id=tenant_id,
                    agent_id=str(agent_id),
                    estimated_tokens=1,
                )
                if not budget_result.allowed:
                    logger.warning(
                        "budget exceeded for tenant %s agent %s: %s",
                        tenant_id,
                        agent_id,
                        budget_result.reason,
                    )
                    return None

            # Get first pending task
            # Note: This is a placeholder - actual implementation would
            # query a task queue table
            pending = await self._get_pending_tasks(session, agent_id, tenant_id, limit=1)

            if not pending:
                return None

            task = pending[0]

            # Mark task as assigned
            # TODO: Update task status in database

            # Build context
            from src.core.company.context import AgentExecutionContext, GoalChain

            context = AgentExecutionContext(
                tenant_id=tenant_id,
                company_id=agent.company_id,
                department_id=agent.department_id,
                task_id=uuid.uuid4(),
                trace_id=uuid.uuid4(),
                goal_chain=GoalChain(),
            )

            # Extract task fields with proper typing and defaults
            task_id_val = task.get("task_id")
            task_id = cast(uuid.UUID, task_id_val) if task_id_val else uuid.uuid4()

            action_val = task.get("action") or task.get("type") or task.get("title")
            action = str(action_val) if action_val else ""

            input_val = task.get("input")
            input_dict = (
                cast(dict[str, Any], input_val)  # TODO(TYPE): replace Any with concrete type
                if input_val
                else {}  # TODO(TYPE): replace Any with concrete type
            )  # TODO(TYPE): replace Any with concrete type

            return TaskNextResponse(
                task_id=task_id,
                action=action,
                input=input_dict,
                context=context,
                sla_seconds=300,  # 5 minute default SLA
            )

    async def complete_task(
        self,
        agent_id: uuid.UUID,
        task_id: uuid.UUID,
        data: TaskCompleteRequest,
        api_key: str | None = None,
    ) -> None:
        """Mark task as completed.

        Args:
            agent_id: Agent UUID
            task_id: Task UUID
            data: Completion data including output and reasoning
            api_key: API key for bcrypt verification. None means internal/trusted caller
                (no API-key auth layer involved) -- any explicit value (including "")
                must verify and fails closed.

        Raises:
            NotFoundError: If task not found
            ValidationError: If output is invalid
        """
        if self.tenant_context is None:
            raise ValueError("Tenant context required")
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant ID is required")

        async with self.db_manager.get_session() as session:
            if api_key is not None:
                agent = await self._get_agent(session, agent_id, tenant_id)
                if agent is None:
                    raise NotFoundError(f"Agent {agent_id} not found")
                if not api_key or not bcrypt.checkpw(api_key.encode(), agent.api_key_hash.encode()):
                    raise AuthError("Invalid API key")

            # Verify agent owns this task
            task = await self._get_task(session, task_id, tenant_id)
            if task is None:
                raise NotFoundError(f"Task {task_id} not found")

            task_agent = getattr(task, "assigned_agent_id", getattr(task, "agent_id", None))
            if str(task_agent) != str(agent_id):
                raise AuthError("Task not assigned to this agent", status_code=403)

            # Validate output size
            output_size = len(str(data.output).encode("utf-8"))
            if output_size > self.MAX_OUTPUT_SIZE:
                raise ValidationError(
                    f"Output size {output_size} exceeds maximum {self.MAX_OUTPUT_SIZE}"
                )

            # Validate output with PolicyEngine
            # TODO: Implement policy validation

            # Update task
            task.status = data.status
            if hasattr(task, "result"):
                task.result = data.output
            if hasattr(task, "output"):
                task.output = data.output
            if hasattr(task, "reasoning_trace"):
                task.reasoning_trace = data.reasoning_trace
            task.completed_at = datetime.now(timezone.utc)

            # Update agent metrics
            agent = await self._get_agent(session, agent_id, tenant_id)
            if agent:
                if data.status == "completed":
                    agent.metrics["tasks_completed"] = agent.metrics.get("tasks_completed", 0) + 1
                else:
                    agent.metrics["tasks_failed"] = agent.metrics.get("tasks_failed", 0) + 1

            await session.commit()
            return None

    async def check_stale_agents(self) -> list[uuid.UUID]:
        """Check for and mark stale agents.

        Returns: List[Any] of agent IDs that were marked stale  # TODO(TYPE): replace Any with concrete type
        """
        if self.tenant_context is None:
            raise ValueError("Tenant context required")
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant ID is required")
        stale_ids: list[uuid.UUID] = []
        async with self.db_manager.get_session() as session:
            # Find agents that haven't sent heartbeat
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)

            result = await session.execute(
                select(ExternalAgent).where(
                    ExternalAgent.tenant_id == tenant_id,
                    ExternalAgent.status.in_(["active", "busy"]),
                    ExternalAgent.last_heartbeat_at < cutoff,
                )
            )
            agents = result.scalars().all()

            for agent in agents:
                # Skip if no heartbeat recorded
                if agent.last_heartbeat_at is None:
                    continue
                # Check if truly stale (2x interval)
                interval_seconds = agent.heartbeat_interval_seconds
                # Ensure non-None value for interval
                effective_interval = 30 if interval_seconds is None else interval_seconds
                stale_threshold = agent.last_heartbeat_at + timedelta(
                    seconds=effective_interval * self.STALE_MULTIPLIER
                )

                if datetime.now(timezone.utc) > stale_threshold:
                    # Increment missed count
                    missed = (getattr(agent, "missed_heartbeat_count", 0) or 0) + 1
                    agent.missed_heartbeat_count = missed

                    if missed >= self.DEAD_MISSES:
                        agent.status = "dead"
                        # Reschedule orphaned tasks
                        await self._reschedule_orphaned_tasks(session, agent.id, tenant_id)
                    else:
                        agent.status = "stale"

                    stale_ids.append(agent.id)

            await session.commit()

        return stale_ids

    async def list_agents(self, limit: int = 50, offset: int = 0) -> list[ExternalAgentResponse]:
        """List all external agents for tenant.

        Returns: List[Any] of ExternalAgentResponse  # TODO(TYPE): replace Any with concrete type
        """
        if self.tenant_context is None:
            raise ValueError("Tenant context required")
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant ID is required")

        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(ExternalAgent)
                .where(
                    ExternalAgent.tenant_id == tenant_id,
                    ExternalAgent.status != "deregistered",
                )
                .limit(limit)
                .offset(offset)
            )
            agents = result.scalars().all()

            return [
                ExternalAgentResponse(
                    agent_id=agent.id,
                    name=agent.name,
                    runtime=agent.runtime,
                    capabilities=agent.capabilities,
                    status=agent.status,
                    last_heartbeat_at=agent.last_heartbeat_at,
                    metrics=agent.metrics,
                )
                for agent in agents
            ]

    async def deregister(self, agent_id: uuid.UUID) -> None:
        """Deregister an agent (soft delete).

        Args:
            agent_id: Agent UUID
        """
        if self.tenant_context is None:
            raise ValueError("Tenant context required")
        tenant_id = self.tenant_context.tenant_id
        if tenant_id is None:
            raise ValueError("Tenant ID is required")

        async with self.db_manager.get_session() as session:
            agent = await self._get_agent(session, agent_id, tenant_id)
            if agent is None:
                raise NotFoundError(f"Agent {agent_id} not found")

            # Soft delete
            agent.status = "deregistered"

            # Cancel pending tasks
            await self._cancel_pending_tasks(session, agent_id, tenant_id)

            await session.commit()

    # ========================================================================
    # Private Methods
    # ========================================================================

    async def _get_agent(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
        tenant_id: int,
    ) -> ExternalAgent | None:
        """Get agent by ID with tenant check."""
        result = await session.execute(
            select(ExternalAgent).where(
                ExternalAgent.id == agent_id,
                ExternalAgent.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_task(
        self,
        session: AsyncSession,
        task_id: uuid.UUID,
        tenant_id: int,
    ) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Get task by ID with tenant check."""
        from src.domains.tasks.models import Task

        result = await session.execute(
            select(Task).where(
                Task.id == task_id,
                Task.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_pending_tasks(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
        tenant_id: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get pending tasks for agent with tenant check."""
        from src.domains.tasks.models import Task, TaskStatus

        result = await session.execute(
            select(Task)
            .where(
                Task.tenant_id == tenant_id,
                Task.assigned_agent_id == str(agent_id),
                Task.status.in_([TaskStatus.PENDING.value, "pending", "assigned"]),
            )
            .order_by(Task.created_at.asc())
            .limit(limit)
        )
        tasks = result.scalars().all()
        return [
            {
                "id": str(t.id),
                "task_id": str(t.id),
                "title": t.title,
                "description": t.description,
                "action": (t.payload or {}).get("action") or (t.payload or {}).get("type") or t.title,
                "type": (t.payload or {}).get("type", "general"),
                "input": t.payload or {},
                "priority": t.priority,
            }
            for t in tasks
        ]

    async def _reschedule_orphaned_tasks(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
        tenant_id: int,
    ) -> None:
        """Reschedule tasks from dead agent with tenant check."""
        from src.domains.tasks.models import Task, TaskStatus

        await session.execute(
            update(Task)
            .where(
                Task.tenant_id == tenant_id,
                Task.assigned_agent_id == str(agent_id),
                Task.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value, "pending", "running", "assigned"]),
            )
            .values(
                assigned_agent_id=None,
                status=TaskStatus.PENDING.value,
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def _cancel_pending_tasks(
        self,
        session: AsyncSession,
        agent_id: uuid.UUID,
        tenant_id: int,
    ) -> None:
        """Cancel pending tasks for deregistered agent with tenant check."""
        from src.domains.tasks.models import Task, TaskStatus

        await session.execute(
            update(Task)
            .where(
                Task.tenant_id == tenant_id,
                Task.assigned_agent_id == str(agent_id),
                Task.status.in_([TaskStatus.PENDING.value, "pending", "assigned"]),
            )
            .values(
                status=TaskStatus.CANCELLED.value,
                updated_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    def _generate_api_key() -> str:
        """Generate a secure API key.

        Returns:
            API key with sk- prefix
        """
        token = secrets.token_urlsafe(32)
        return f"sk-{token}"
